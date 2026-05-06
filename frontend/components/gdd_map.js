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
  let lastZoom = null;
  let currentRasterUrl = null;
  let currentYear = null;
  let currentCrop = null;

  // Frost-event count colour scale:
  //  < 0  → light grey  (never reached budbreak — too cold for crop to develop)
  //    0  → green       (reached budbreak, no frost events)
  //    1  → blue        (1 frost event)
  //   2+  → orange → dark red (increasing risk)
  const getFrostColor = (count) => {
    if (count == null || isNaN(count)) return null;
    if (count < 0) return 'rgba(190, 190, 190, 0.60)';
    const c = Math.round(count);
    if (c === 0) return 'rgba(45, 138, 78, 0.55)';
    if (c === 1) return 'rgba(59, 130, 246, 0.75)';
    const t = Math.min((c - 2) / 6, 1);
    return chroma.mix('#f97316', '#7f1d1d', t, 'lab').alpha(0.82).css();
  };

  window.loadGDDRaster = function (baseUrl, year, crop) {
    if (isLoading) return;
    isLoading = true;
    currentRasterUrl = baseUrl;
    currentYear = year;
    currentCrop = crop;

    document.getElementById('loading').style.display = 'block';

    const zoom = map.getZoom();
    const bustUrl = baseUrl + '&zoom_level=' + zoom + '&_cache=' + Date.now();
    const prevLayer = currentLayer;
    currentLayer = null;

    fetch(bustUrl)
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.arrayBuffer(); })
      .then(ab => { if (!ab || ab.byteLength === 0) throw new Error('Empty raster'); return parseGeoraster(ab); })
      .then(georaster => {
        if (prevLayer) { try { map.removeLayer(prevLayer); } catch (_) {} }

        currentLayer = new GeoRasterLayer({
          georaster,
          opacity: 1,
          pixelValuesToColorFn: values => getFrostColor(values[0]),
          resolution: 256,
          updateWhenZooming: false,
        });
        currentLayer.addTo(map);

        if (lastZoom === null) {
          map.fitBounds(currentLayer.getBounds());
        }
        lastZoom = zoom;

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

  // Zoom: re-fetch when crossing resolution thresholds (same logic as heatmap map)
  map.on('zoomend', function () {
    if (!currentRasterUrl || isLoading) return;
    const newZoom = map.getZoom();
    let refetch = false;
    if (lastZoom === null) refetch = true;
    else if (lastZoom < 4 && newZoom >= 4) refetch = true;
    else if (lastZoom < 8 && newZoom >= 8) refetch = true;
    else if (lastZoom >= 8 && newZoom < 8) refetch = true;
    else if (lastZoom >= 4 && newZoom < 4) refetch = true;
    if (refetch) {
      window.loadGDDRaster(currentRasterUrl, currentYear, currentCrop);
    }
  });

  // Click: send coordinate to parent Dash frame for future detail panel
  map.on('click', function (e) {
    const lat = e.latlng.lat.toFixed(4);
    const lon = (((e.latlng.lng + 180) % 360) - 180).toFixed(4);
    window.parent.postMessage({
      type: 'gddCoordinateClicked',
      lat: parseFloat(lat),
      lon: parseFloat(lon),
    }, '*');
  });

  // Accept commands from parent Dash frame
  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'loadGDDRaster') {
      window.loadGDDRaster(e.data.rasterUrl, e.data.year, e.data.crop);
    }
  });
})();
