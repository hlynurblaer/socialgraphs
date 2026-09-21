// Shared map-drawing logic for the UN member-state network pages (un.html,
// game.html, and any future page that needs the same map). Owns the parts
// that took real, hard-won effort to get right and that MUST stay identical
// everywhere they're used -- coordinate resolution for every country
// (including the exclave/antimeridian/concave-shape special cases), the
// world-atlas load, and drawing the base map (ocean, country polygons, all
// edges, markers). Callers attach their own hover/click behavior and decide
// which edges to show/color -- that part is legitimately different per page
// (un.html's hover-preview-and-pin vs. game.html's click-to-move), so it
// stays in each page's own script rather than being forced in here.
//
// Usage:
//   <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
//   <script src="https://cdn.jsdelivr.net/npm/topojson-client@3/dist/topojson-client.min.js"></script>
//   <script src="map-common.js"></script>
//   <script>
//     (async function () {
//       const built = await MapCommon.buildMap({ svgSelector: "#map" });
//       // built.nodes, built.markers, built.countryPaths, built.edgePaths, ...
//     })();
//   </script>

window.MapCommon = (function () {
  "use strict";

  const NODES_URL = "./data/un_nodes.tsv";
  const EDGES_URL = "./data/un_edges.tsv";
  const WORLD_ATLAS_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json";

  // Wikipedia country-article name (the tsv "name" column) -> the exact
  // name string world-atlas's countries-50m.json uses for the matching
  // polygon. Built by diffing the live 193-country node list against the
  // topojson's own properties.name values -- not guessed: 168 of 193
  // matched by exact string already, these are the 24 explicit exceptions
  // (abbreviations, alternate spellings, or an accent Natural Earth drops).
  const NAME_ALIASES = {
    "Antigua and Barbuda": "Antigua and Barb.",
    "Bosnia and Herzegovina": "Bosnia and Herz.",
    "Cape Verde": "Cabo Verde",
    "Central African Republic": "Central African Rep.",
    "Czech Republic": "Czechia",
    "Democratic Republic of the Congo": "Dem. Rep. Congo",
    "Dominican Republic": "Dominican Rep.",
    "Equatorial Guinea": "Eq. Guinea",
    "Eswatini": "eSwatini",
    "Federated States of Micronesia": "Micronesia",
    "Georgia (country)": "Georgia",
    "Ivory Coast": "Côte d'Ivoire",
    "Marshall Islands": "Marshall Is.",
    "North Macedonia": "Macedonia",
    "Republic of Ireland": "Ireland",
    "Republic of the Congo": "Congo",
    "Saint Kitts and Nevis": "St. Kitts and Nevis",
    "Saint Vincent and the Grenadines": "St. Vin. and Gren.",
    "Solomon Islands": "Solomon Is.",
    "South Sudan": "S. Sudan",
    "São Tomé and Príncipe": "São Tomé and Principe",
    "The Bahamas": "Bahamas",
    "The Gambia": "Gambia",
    "United States": "United States of America",
  };

  // Hand-filled coordinate overrides, checked against the live file and
  // verified to land inside the country's own polygon (not eyeballed).
  // [lon, lat], from Wikidata's P625 "coordinate location" for the country
  // item. Two different reasons a country ends up here:
  //
  //  - No matching polygon at all (only Tuvalu, of all 193, as of writing).
  //  - A polygon exists, but d3.geoCentroid(feature) -- the area-weighted
  //    centroid across every ring in the country's MultiPolygon -- lands
  //    somewhere wrong. This 50m dataset bundles some countries' overseas
  //    territories into the SAME feature as the mainland (e.g. France's
  //    "France" polygon also includes French Guiana, Réunion, Guadeloupe,
  //    Martinique, Mayotte), which drags the naive centroid far off; that
  //    general case is instead handled automatically by computing the
  //    centroid of just the largest-area ring (see dominantRingCentroid
  //    below), so France etc. don't need an entry here. The countries
  //    below are a *different, narrower* failure: their own single main
  //    landmass is concave enough (Croatia's crescent around Bosnia's
  //    Neum corridor; Vietnam's S-curve; Israel's shape against the West
  //    Bank) that even the dominant ring's own area centroid falls just
  //    outside the country -- confirmed by checking it lands inside a
  //    neighboring country's polygon instead. Verified with d3.geoContains
  //    against this exact topojson before being hardcoded.
  //
  // Keyed by node_id. If a future CDN update drops other countries'
  // polygons, they'll be logged to the console (see below) rather than
  // silently missing a marker -- add entries here as needed.
  const MANUAL_COORDS = {
    "Tuvalu": [178.005556, -7.475],
    "Croatia": [15.466667, 45.25],
    "Israel": [35, 31],
    "Vietnam": [108, 16],
  };

  // Tonga, Samoa and Kiribati sit just east of the antimeridian (roughly
  // -175, -172 and -157 to 172 degrees longitude), which on this 0-centered
  // projection puts them at the FAR LEFT edge of the map -- while Fiji,
  // Vanuatu and the rest of the Pacific-islands cluster (all just west of
  // the antimeridian) land at the far RIGHT edge. Same real-world
  // neighborhood, opposite edges of the rendered map: there is no single
  // rotation of this projection that fixes that for these three without
  // moving the seam somewhere else inconvenient (through Europe/Africa).
  // Instead of a global rotation, these three get an explicit SCREEN-SPACE
  // position (world units, post-projection, in the extra padding added to
  // the right of the map -- see PACIFIC_PAD below) placed next to the rest
  // of the Pacific cluster. Their actual landmass polygons stay in their
  // true (left-edge) position; only the marker/edge endpoint moves, same
  // as every other manual override, just in pixel space instead of lon/lat.
  const PACIFIC_PIXEL_OVERRIDES = {
    "Kiribati": [1030, 288],
    "Samoa": [1000, 330],
    "Tonga": [978, 362],
  };
  const PACIFIC_PAD = 100;

  // Continent for each of the 193 member states, from Wikidata's P30
  // "continent" claim (fetched via a batched SPARQL query against all 193
  // wikidata_ids, cross-checked for coverage -- every node_id below has an
  // entry). A handful of countries carry more than one P30 value; resolved
  // by hand using the conventional single-continent classification rather
  // than an arbitrary pick: Turkey and Kazakhstan -> Asia (predominant
  // landmass), Russia -> Europe (conventional grouping despite Asian
  // majority landmass). "Insular Oceania" (Fiji, Vanuatu's secondary P30
  // value) is folded into plain "Oceania".
  const CONTINENT_BY_ID = {
    "Afghanistan": "Asia", "Albania": "Europe", "Algeria": "Africa", "Andorra": "Europe",
    "Angola": "Africa", "Antigua_and_Barbuda": "North America", "Argentina": "South America", "Armenia": "Asia",
    "Australia": "Oceania", "Austria": "Europe", "Azerbaijan": "Asia", "Bahrain": "Asia",
    "Bangladesh": "Asia", "Barbados": "North America", "Belarus": "Europe", "Belgium": "Europe",
    "Belize": "North America", "Benin": "Africa", "Bhutan": "Asia", "Bolivia": "South America",
    "Bosnia_and_Herzegovina": "Europe", "Botswana": "Africa", "Brazil": "South America", "Brunei": "Asia",
    "Bulgaria": "Europe", "Burkina_Faso": "Africa", "Burundi": "Africa", "Cambodia": "Asia",
    "Cameroon": "Africa", "Canada": "North America", "Cape_Verde": "Africa", "Central_African_Republic": "Africa",
    "Chad": "Africa", "Chile": "South America", "China": "Asia", "Colombia": "South America",
    "Comoros": "Africa", "Costa_Rica": "North America", "Croatia": "Europe", "Cuba": "North America",
    "Cyprus": "Europe", "Czech_Republic": "Europe", "Democratic_Republic_of_the_Congo": "Africa", "Denmark": "Europe",
    "Djibouti": "Africa", "Dominica": "North America", "Dominican_Republic": "North America", "Ecuador": "South America",
    "Egypt": "Africa", "El_Salvador": "North America", "Equatorial_Guinea": "Africa", "Eritrea": "Africa",
    "Estonia": "Europe", "Eswatini": "Africa", "Ethiopia": "Africa", "Federated_States_of_Micronesia": "Oceania",
    "Fiji": "Oceania", "Finland": "Europe", "France": "Europe", "Gabon": "Africa",
    "Georgia_(country)": "Europe", "Germany": "Europe", "Ghana": "Africa", "Greece": "Europe",
    "Grenada": "North America", "Guatemala": "North America", "Guinea": "Africa", "Guinea-Bissau": "Africa",
    "Guyana": "South America", "Haiti": "North America", "Honduras": "North America", "Hungary": "Europe",
    "Iceland": "Europe", "India": "Asia", "Indonesia": "Asia", "Iran": "Asia",
    "Iraq": "Asia", "Israel": "Asia", "Italy": "Europe", "Ivory_Coast": "Africa",
    "Jamaica": "North America", "Japan": "Asia", "Jordan": "Asia", "Kazakhstan": "Asia",
    "Kenya": "Africa", "Kiribati": "Oceania", "Kuwait": "Asia", "Kyrgyzstan": "Asia",
    "Laos": "Asia", "Latvia": "Europe", "Lebanon": "Asia", "Lesotho": "Africa",
    "Liberia": "Africa", "Libya": "Africa", "Liechtenstein": "Europe", "Lithuania": "Europe",
    "Luxembourg": "Europe", "Madagascar": "Africa", "Malawi": "Africa", "Malaysia": "Asia",
    "Maldives": "Asia", "Mali": "Africa", "Malta": "Europe", "Marshall_Islands": "Oceania",
    "Mauritania": "Africa", "Mauritius": "Africa", "Mexico": "North America", "Moldova": "Europe",
    "Monaco": "Europe", "Mongolia": "Asia", "Montenegro": "Europe", "Morocco": "Africa",
    "Mozambique": "Africa", "Myanmar": "Asia", "Namibia": "Africa", "Nauru": "Oceania",
    "Nepal": "Asia", "Netherlands": "Europe", "New_Zealand": "Oceania", "Nicaragua": "North America",
    "Niger": "Africa", "Nigeria": "Africa", "North_Korea": "Asia", "North_Macedonia": "Europe",
    "Norway": "Europe", "Oman": "Asia", "Pakistan": "Asia", "Palau": "Oceania",
    "Panama": "North America", "Papua_New_Guinea": "Oceania", "Paraguay": "South America", "Peru": "South America",
    "Philippines": "Asia", "Poland": "Europe", "Portugal": "Europe", "Qatar": "Asia",
    "Republic_of_Ireland": "Europe", "Republic_of_the_Congo": "Africa", "Romania": "Europe", "Russia": "Europe",
    "Rwanda": "Africa", "Saint_Kitts_and_Nevis": "North America", "Saint_Lucia": "North America", "Saint_Vincent_and_the_Grenadines": "North America",
    "Samoa": "Oceania", "San_Marino": "Europe", "Saudi_Arabia": "Asia", "Senegal": "Africa",
    "Serbia": "Europe", "Seychelles": "Africa", "Sierra_Leone": "Africa", "Singapore": "Asia",
    "Slovakia": "Europe", "Slovenia": "Europe", "Solomon_Islands": "Oceania", "Somalia": "Africa",
    "South_Africa": "Africa", "South_Korea": "Asia", "South_Sudan": "Africa", "Spain": "Europe",
    "Sri_Lanka": "Asia", "Sudan": "Africa", "Suriname": "South America", "Sweden": "Europe",
    "Switzerland": "Europe", "Syria": "Asia", "São_Tomé_and_Príncipe": "Africa", "Tajikistan": "Asia",
    "Tanzania": "Africa", "Thailand": "Asia", "The_Bahamas": "North America", "The_Gambia": "Africa",
    "Timor-Leste": "Asia", "Togo": "Africa", "Tonga": "Oceania", "Trinidad_and_Tobago": "North America",
    "Tunisia": "Africa", "Turkey": "Asia", "Turkmenistan": "Asia", "Tuvalu": "Oceania",
    "Uganda": "Africa", "Ukraine": "Europe", "United_Arab_Emirates": "Asia", "United_Kingdom": "Europe",
    "United_States": "North America", "Uruguay": "South America", "Uzbekistan": "Asia", "Vanuatu": "Oceania",
    "Venezuela": "South America", "Vietnam": "Asia", "Yemen": "Asia", "Zambia": "Africa",
    "Zimbabwe": "Africa",
  };

  // For a MultiPolygon feature, geoCentroid area-weights across every ring
  // -- including small, far-flung exclaves -- which is exactly what drags
  // countries like France off into the ocean or a neighboring country. Use
  // the centroid of just the single largest-area ring instead: a country's
  // own main landmass, not diluted by its overseas territories.
  function dominantRingCentroid(feature) {
    if (feature.geometry.type !== "MultiPolygon") return d3.geoCentroid(feature);
    let best = null, bestArea = -1;
    feature.geometry.coordinates.forEach(polygonCoords => {
      const single = { type: "Feature", geometry: { type: "Polygon", coordinates: polygonCoords }, properties: {} };
      const area = d3.geoArea(single);
      if (area > bestArea) { bestArea = area; best = single; }
    });
    return d3.geoCentroid(best);
  }

  function stripComments(text) {
    return text.split("\n").filter(line => !line.startsWith("#"));
  }

  async function loadTSV(url, forcedHeader) {
    const raw = await d3.text(url);
    const lines = stripComments(raw);
    const body = forcedHeader ? [forcedHeader, ...lines] : lines;
    return d3.tsvParse(body.join("\n"));
  }

  function showError(message) {
    const errorBanner = document.getElementById("error-banner");
    if (!errorBanner) { console.error(message); return; }
    errorBanner.innerHTML = message;
    errorBanner.hidden = false;
  }

  const FILE_URL_HELP =
    "This page fetches <code>data/un_nodes.tsv</code> and <code>data/un_edges.tsv</code>, " +
    "which browsers block over a plain <code>file://</code> URL. Serve this folder locally, e.g. " +
    "<code>python3 -m http.server 8000</code> from the UN/ folder, then open " +
    "<code>http://localhost:8000/un.html</code>.";

  async function loadNetworkData() {
    const [nodesRaw, edgesRaw] = await Promise.all([
      loadTSV(NODES_URL),                    // nodes file already has a real header row
      loadTSV(EDGES_URL, "source\ttarget"),  // edges file's header line is commented out
    ]);

    const nodes = nodesRaw.map(d => ({
      node_id: d.node_id,
      name: d.name,
      wikidata_id: d.wikidata_id,
      url: d.url,
      description: d.description,
    }));
    const nodesById = new Map(nodes.map(n => [n.node_id, n]));

    const edges = edgesRaw
      .filter(e => nodesById.has(e.source) && nodesById.has(e.target))
      .map(e => ({ source: e.source, target: e.target }));

    const edgeKeySet = new Set(edges.map(e => e.source + "|" + e.target));
    const isMutual = (a, b) => edgeKeySet.has(a + "|" + b) && edgeKeySet.has(b + "|" + a);

    const outDegree = new Map(nodes.map(n => [n.node_id, 0]));
    const inDegree = new Map(nodes.map(n => [n.node_id, 0]));
    const outAdjacency = new Map(nodes.map(n => [n.node_id, new Set()]));
    const inAdjacency = new Map(nodes.map(n => [n.node_id, new Set()]));
    edges.forEach(e => {
      outDegree.set(e.source, outDegree.get(e.source) + 1);
      inDegree.set(e.target, inDegree.get(e.target) + 1);
      outAdjacency.get(e.source).add(e.target);
      inAdjacency.get(e.target).add(e.source);
    });

    function rankBy(getValue) {
      const sorted = [...nodes].sort((a, b) => {
        const da = getValue(a.node_id), db = getValue(b.node_id);
        if (db !== da) return db - da;
        return a.name.localeCompare(b.name);
      });
      return new Map(sorted.map((n, i) => [n.node_id, i + 1]));
    }
    const totalRankById = rankBy(id => outDegree.get(id) + inDegree.get(id));
    const outRankById = rankBy(id => outDegree.get(id));
    const inRankById = rankBy(id => inDegree.get(id));

    return {
      nodes, nodesById, edges, outDegree, inDegree, edgeKeySet, isMutual,
      outAdjacency, inAdjacency, totalRankById, outRankById, inRankById,
    };
  }

  async function loadWorldAtlas() {
    return d3.json(WORLD_ATLAS_URL);
  }

  function buildGeography(world, nodes) {
    const countriesGeo = topojson.feature(world, world.objects.countries);
    const landByName = new Map(countriesGeo.features.map(f => [f.properties.name, f]));

    const topoNameToNodeId = new Map();
    const coordsByNodeId = new Map();
    const unmatched = [];

    nodes.forEach(n => {
      const topoName = NAME_ALIASES[n.name] || n.name;
      const feature = landByName.get(topoName);
      if (feature) topoNameToNodeId.set(topoName, n.node_id); // land hover/click works either way

      if (MANUAL_COORDS[n.node_id]) {
        coordsByNodeId.set(n.node_id, MANUAL_COORDS[n.node_id]);
      } else if (feature) {
        coordsByNodeId.set(n.node_id, dominantRingCentroid(feature));
      } else {
        unmatched.push(n.node_id);
      }
    });

    if (unmatched.length) {
      console.warn(
        `${unmatched.length} node(s) have no coordinates (no topojson match and no manual ` +
        `fallback) -- their markers are skipped rather than guessed at:`, unmatched
      );
    }

    return { countriesGeo, topoNameToNodeId, coordsByNodeId, unmatched };
  }

  // ---- decorative header emblem: azimuthal-equidistant land silhouette ----
  // Purely a nod to the UN emblem's own north-polar projection -- used only
  // for this small static icon, never for the interactive map itself, since
  // that projection badly distorts the southern hemisphere.
  function drawEmblem(world, selector) {
    selector = selector || "#emblem-land";
    const landGeo = topojson.feature(world, world.objects.land);
    const size = 27;
    const emblemProjection = d3.geoAzimuthalEquidistant()
      .rotate([0, -90])
      .clipAngle(180 - 1e-3)
      .translate([32, 30])
      .scale(size);
    const emblemPath = d3.geoPath(emblemProjection);
    d3.select(selector)
      .selectAll("path")
      .data(landGeo.features)
      .join("path")
      .attr("class", "land")
      .attr("d", emblemPath);
  }

  function edgePathD(nodeScreenPos, e) {
    const s = nodeScreenPos(e.source), t = nodeScreenPos(e.target);
    if (!s || !t) return null;
    const [x1, y1] = s, [x2, y2] = t;
    const dx = x2 - x1, dy = y2 - y1;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    // gentle perpendicular bow so overlapping edges stay visually separable
    const bow = Math.min(dist * 0.14, 40);
    const mx = (x1 + x2) / 2 - (dy / dist) * bow;
    const my = (y1 + y2) / 2 + (dx / dist) * bow;
    return `M${x1},${y1} Q${mx},${my} ${x2},${y2}`;
  }

  // Builds the full base map (data, geography, ocean, country polygons, all
  // edges, markers, emblem, zoom/pan) onto the given <svg>. Returns
  // everything a page needs to layer its own interactivity on top -- no
  // hover/click listeners are attached here (that's page-specific), and no
  // edge is colored/shown by default (every page decides that for itself).
  async function buildMap(opts) {
    opts = opts || {};
    const svgSelector = opts.svgSelector || "#map";
    const emblemSelector = opts.emblemSelector || "#emblem-land";

    let data, world;
    try {
      [data, world] = await Promise.all([loadNetworkData(), loadWorldAtlas()]);
    } catch (err) {
      console.error("Failed to load map data:", err);
      showError("Could not load the network data. " + FILE_URL_HELP);
      throw err;
    }

    const geo = buildGeography(world, data.nodes);

    const width = 960, height = 520;
    const totalWidth = width + PACIFIC_PAD; // extra ocean padding on the right, see PACIFIC_PIXEL_OVERRIDES above
    const fitFeatures = {
      type: "FeatureCollection",
      features: geo.countriesGeo.features.filter(f => f.properties.name !== "Antarctica"),
    };
    // fitSize uses the ORIGINAL width, not totalWidth -- the extra padding is
    // blank canvas bolted on the side, not extra room the map itself scales
    // into (which would shrink/distort every other country to compensate).
    const projection = d3.geoNaturalEarth1().fitSize([width, height], fitFeatures);

    function nodeScreenPos(nodeId) {
      if (PACIFIC_PIXEL_OVERRIDES[nodeId]) return PACIFIC_PIXEL_OVERRIDES[nodeId];
      const coords = geo.coordsByNodeId.get(nodeId);
      return coords ? projection(coords) : null;
    }

    const svg = d3.select(svgSelector);

    svg.append("rect")
      .attr("width", totalWidth).attr("height", height)
      .attr("fill", "var(--map-ocean)");

    // Everything pannable/zoomable lives in this one group; the ocean rect
    // above stays fixed so panning never reveals blank canvas past its edge.
    const zoomLayer = svg.append("g").attr("class", "zoom-layer");
    const gCountries = zoomLayer.append("g").attr("class", "countries");
    const gEdges = zoomLayer.append("g").attr("class", "edges");
    const gMarkers = zoomLayer.append("g").attr("class", "markers");

    const path = d3.geoPath(projection);
    const countryPaths = gCountries.selectAll("path.country")
      .data(geo.countriesGeo.features)
      .join("path")
      .attr("class", f => "country" + (geo.topoNameToNodeId.has(f.properties.name) ? " member" : ""))
      .attr("d", path);

    drawEmblem(world, emblemSelector);

    const drawableEdges = data.edges
      .map(e => ({ ...e, d: edgePathD(nodeScreenPos, e) }))
      .filter(e => e.d !== null);

    if (drawableEdges.length !== data.edges.length) {
      console.warn(
        `${data.edges.length - drawableEdges.length} edge(s) skipped -- one endpoint has no coordinates.`
      );
    }

    const edgePaths = gEdges.selectAll("path.edge")
      .data(drawableEdges)
      .join("path")
      .attr("class", "edge")
      .attr("d", d => d.d);

    const markerNodes = data.nodes.filter(n => geo.coordsByNodeId.has(n.node_id));
    const BASE_R = 3.4, FOCUSED_R = 6, MIN_R = 1.2;

    const markers = gMarkers.selectAll("circle.marker")
      .data(markerNodes)
      .join("circle")
      .attr("class", "marker")
      .attr("r", BASE_R)
      .attr("cx", n => nodeScreenPos(n.node_id)[0])
      .attr("cy", n => nodeScreenPos(n.node_id)[1])
      .style("cursor", "pointer");

    markers.append("title").text(n => n.name);

    // -------------------------------------------------------------- zoom --
    // Marker radius is defined in world units, same as everything else in
    // zoomLayer -- so without rescaling, zooming in also visually inflates
    // every dot by the zoom factor, until the map is just a blob of
    // overlapping circles with no country outlines visible underneath.
    // Callers combine markerRadiusFor(isFocused) with their own per-node
    // "is this focused" logic inside onZoomTick / their own render.
    let currentZoomK = 1;
    function markerRadiusFor(isFocused) {
      return Math.max(MIN_R, (isFocused ? FOCUSED_R : BASE_R) / currentZoomK);
    }

    const zoom = d3.zoom()
      .scaleExtent([1, 10])
      .translateExtent([[0, 0], [totalWidth, height]])
      .on("zoom", (event) => {
        zoomLayer.attr("transform", event.transform);
        currentZoomK = event.transform.k;
        if (typeof opts.onZoomTick === "function") opts.onZoomTick(currentZoomK);
      });

    svg.call(zoom);

    // Generic "widen the pannable area by N extra CSS pixels" utility -- used
    // by un.html so its slide-in side panel doesn't permanently hide a strip
    // of map behind it (see the comment on #side-panel's pointer-events for
    // the related hover-flicker fix). Pass 0 to reset to the normal extent.
    function setExtraPanWidth(extraCssPx) {
      const svgRect = svg.node().getBoundingClientRect();
      const cssPerWorldUnit = svgRect.width / totalWidth;
      const extra = cssPerWorldUnit > 0 ? (extraCssPx || 0) / cssPerWorldUnit : 0;
      zoom.translateExtent([[0, 0], [totalWidth + extra, height]]);
    }

    const zoomInBtn = document.getElementById("zoom-in");
    const zoomOutBtn = document.getElementById("zoom-out");
    const zoomResetBtn = document.getElementById("zoom-reset");
    if (zoomInBtn) zoomInBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      svg.transition().duration(200).call(zoom.scaleBy, 1.6);
    });
    if (zoomOutBtn) zoomOutBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      svg.transition().duration(200).call(zoom.scaleBy, 1 / 1.6);
    });
    if (zoomResetBtn) zoomResetBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
    });

    console.log(`Loaded ${data.nodes.length} nodes and ${data.edges.length} edges.`);

    return {
      // data
      nodes: data.nodes, nodesById: data.nodesById, edges: data.edges,
      outDegree: data.outDegree, inDegree: data.inDegree,
      edgeKeySet: data.edgeKeySet, isMutual: data.isMutual,
      outAdjacency: data.outAdjacency, inAdjacency: data.inAdjacency,
      totalRankById: data.totalRankById, outRankById: data.outRankById, inRankById: data.inRankById,

      // geometry
      countriesGeo: geo.countriesGeo, topoNameToNodeId: geo.topoNameToNodeId,
      coordsByNodeId: geo.coordsByNodeId, unmatched: geo.unmatched,
      projection, nodeScreenPos, width, height, totalWidth,

      // DOM
      svg, zoomLayer, gCountries, gEdges, gMarkers,
      countryPaths, markers, edgePaths, drawableEdges,

      // zoom
      zoom, setExtraPanWidth, getZoomK: () => currentZoomK,
      BASE_R, FOCUSED_R, MIN_R, markerRadiusFor,
    };
  }

  return {
    buildMap,
    loadNetworkData,
    NAME_ALIASES, MANUAL_COORDS, PACIFIC_PIXEL_OVERRIDES, PACIFIC_PAD, CONTINENT_BY_ID,
    dominantRingCentroid, showError,
  };
})();
