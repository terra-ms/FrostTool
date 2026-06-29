(function () {
  const API = window.__API_URL__;

  // Europe centre
  const map = L.map('map', { center: [52, 15], zoom: 4, zoomControl: true });

  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 }
  ).addTo(map);

  let currentLayer = null;
  let isLoading = false;
  let hasRendered = false;
  let currentRasterUrl = null;
  let currentYear = null;
  let currentCrop = null;
  let borderLayer = null;
  let admin1Layer = null;
  const ADMIN1_ZOOM = 5;

  const STATIC = API.replace(/\/?$/, '') + '/static';

  fetch(STATIC + '/ne_admin0.geojson')
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      borderLayer = L.geoJSON(data, {
        style: { color: 'rgba(255,255,255,0.45)', weight: 0.7, fill: false },
      }).addTo(map);
    })
    .catch(e => console.warn('Could not load country borders:', e));

  fetch(STATIC + '/ne_admin1.geojson')
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      admin1Layer = L.geoJSON(data, {
        style: { color: 'rgba(255,255,255,0.28)', weight: 0.5, fill: false },
      });
      if (map.getZoom() >= ADMIN1_ZOOM) admin1Layer.addTo(map);
    })
    .catch(e => console.warn('Could not load province borders:', e));

  // Frost-event count colour scale (solid colours — transparency is handled by layer opacity):
  //  < 0  → light grey  (never reached budbreak — too cold for crop to develop)
  //    0  → green       (reached budbreak, no frost events)
  //    1  → blue        (1 frost event)
  //   2+  → orange → dark red (increasing risk)
  const getFrostColor = (count) => {
    if (count == null || isNaN(count)) return null;
    if (count < 0) return '#bebebe';
    const c = Math.round(count);
    if (c === 0) return '#2d8a4e';
    if (c === 1) return '#3b82f6';
    const t = Math.min((c - 2) / 6, 1);
    return chroma.mix('#f97316', '#7f1d1d', t, 'lab').hex();
  };

  window.loadGDDRaster = function (baseUrl, year, crop) {
    if (isLoading) return;
    isLoading = true;
    currentRasterUrl = baseUrl;
    currentYear = year;
    currentCrop = crop;

    document.getElementById('loading').style.display = 'block';

    const bustUrl = baseUrl + '&_cache=' + Date.now();
    const prevLayer = currentLayer;
    currentLayer = null;

    fetch(bustUrl)
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.arrayBuffer(); })
      .then(ab => { if (!ab || ab.byteLength === 0) throw new Error('Empty raster'); return parseGeoraster(ab); })
      .then(georaster => {
        if (prevLayer) { try { map.removeLayer(prevLayer); } catch (_) {} }

        currentLayer = new GeoRasterLayer({
          georaster,
          opacity: 0.75,
          pixelValuesToColorFn: values => getFrostColor(values[0]),
          resolution: 256,
          updateWhenZooming: true,
        });
        currentLayer.addTo(map);
        if (borderLayer) borderLayer.bringToFront();
        if (admin1Layer && map.hasLayer(admin1Layer)) admin1Layer.bringToFront();

        if (!hasRendered) {
          map.fitBounds(currentLayer.getBounds());
        }
        hasRendered = true;

        const info = document.getElementById('render-info');
        info.textContent = year + '  ·  ' + crop.charAt(0).toUpperCase() + crop.slice(1);
        info.style.display = 'block';

        document.getElementById('loading').style.display = 'none';
        isLoading = false;
      })
      .catch(e => {
        console.error('GDD raster error:', e);
        document.getElementById('loading').style.display = 'none';
        isLoading = false;
        if (prevLayer && !currentLayer) {
          try { currentLayer = prevLayer; map.addLayer(prevLayer); } catch (_) {}
        }
      });
  };


  map.on('zoomend', function () {
    if (admin1Layer) {
      const zoomed = map.getZoom() >= ADMIN1_ZOOM;
      if (zoomed && !map.hasLayer(admin1Layer)) {
        admin1Layer.addTo(map);
        if (borderLayer) borderLayer.bringToFront();
        admin1Layer.bringToFront();
      } else if (!zoomed && map.hasLayer(admin1Layer)) {
        map.removeLayer(admin1Layer);
      }
    }
  });

  // Click: send coordinate + current year/crop to parent Dash frame.
  map.on('click', function (e) {
    if (!currentYear || !currentCrop) return;
    const lat = e.latlng.lat.toFixed(4);
    const lon = (((e.latlng.lng + 180) % 360) - 180).toFixed(4);
    window.parent.postMessage({
      type: 'gddCoordinateClicked',
      lat: parseFloat(lat),
      lon: parseFloat(lon),
      year: currentYear,
      crop: currentCrop,
    }, '*');
  });

  // Accept commands from parent Dash frame
  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'loadGDDRaster') {
      window.loadGDDRaster(e.data.rasterUrl, e.data.year, e.data.crop);
    }
  });
})();
