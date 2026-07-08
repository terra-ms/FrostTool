(function () {
  const API = window.__API_URL__;
  const DEBUG = false;
  const log = (msg, ...args) => { if (DEBUG) console.log(msg, ...args); };

  const map = L.map('map', { center: [20, 0], zoom: 2, zoomControl: true });

  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { attribution: '© OpenStreetMap © CARTO', maxZoom: 19 }
  ).addTo(map);

  let currentLayer = null;
  let currentDate = null;
  let dateRange = null;
  let currentTempType = "mean";
  let vmin = 0, vmax = 1;
  let continentBounds = {};
  let isLoading = false;
  let lastFetchedZoomLevel = null;
  let rasterUrls = {};
  let currentContinent = null;
  let borderLayer = null;
  let admin1Layer = null;
  let _pendingRasterLoad = null;
  const ADMIN1_ZOOM = 5;

  const STATIC = API.replace(/\/?$/, '') + '/static';

  // ── Progress bar ───────────────────────────────────────────────────────────
  const _barWrap  = document.getElementById('progress-bar-wrap');
  const _bar      = document.getElementById('progress-bar');
  const _barLabel = document.getElementById('progress-label');

  function _progressTo(pct, durSecs) {
    if (!_bar) return;
    if (durSecs <= 0) {
      _bar.style.transition = 'none';
      _bar.style.width = pct + '%';
      void _bar.offsetWidth; // force style flush so next transition starts from here
    } else {
      _bar.style.transition = `width ${durSecs}s linear`;
      _bar.style.width = pct + '%';
    }
  }

  function _progressStart(label) {
    if (!_barWrap) return;
    const alreadyVisible = _barWrap.style.display === 'block';
    _barWrap.style.display = 'block';
    if (_barLabel) _barLabel.textContent = label;
    if (!alreadyVisible) {
      _progressTo(0, 0);
      _progressTo(5, 0.3);
    }
  }

  function _progressDone() {
    if (!_barWrap) return;
    _progressTo(100, 0.25);
    setTimeout(() => { _barWrap.style.display = 'none'; _progressTo(0, 0); }, 380);
  }

  function _progressError() {
    if (!_barWrap) return;
    _barWrap.style.display = 'none';
    _progressTo(0, 0);
  }

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
        style: { color: 'rgba(255,255,255,0.25)', weight: 0.5, fill: false },
      }).addTo(map);
      if (map.getZoom() >= ADMIN1_ZOOM) {
        admin1Layer.bringToFront();
        if (borderLayer) borderLayer.bringToFront();
      } else {
        admin1Layer.setStyle({ opacity: 0 });
      }
    })
    .catch(e => console.warn('Could not load province borders:', e));

  // Absolute temperature colour scale: -40°C (blue) → 50°C (dark red)
  const absoluteColorScale = chroma.scale([
    '#00007f', '#0000ff', '#007fff', '#00ffff',
    '#7fff7f',
    '#ffff00',
    '#ff7f00',
    '#ff0000', '#7f0000'
  ]).domain([-40, 50]).mode('lab');

  const getAbsoluteColor = (kelvin) => {
    const celsius = kelvin - 273.15;
    return absoluteColorScale(celsius).hex();
  };

  fetch(API + '/continents')
    .then(r => {
      if (!r.ok) {
        console.error('Continent bounds fetch failed with status:', r.status);
        return {};
      }
      return r.json();
    })
    .then(data => { continentBounds = data || {}; })
    .catch(e => {
      console.error('Failed to load continent bounds:', e);
      continentBounds = {};
    });

  window.loadRaster = function (rasterUrl, colorscaleUrl, date, dateRangeObj, continent, tempType, skipColorscale) {
    if (isLoading) {
      _pendingRasterLoad = {rasterUrl, colorscaleUrl, date, dateRangeObj, continent, tempType};
      return;
    }
    _pendingRasterLoad = null;

    isLoading = true;
    currentDate = date;
    currentTempType = tempType || "mean";
    dateRange = dateRangeObj || null;
    _progressStart(skipColorscale ? 'LOADING RASTER' : 'FETCHING COLORSCALE');
    _progressTo(12, 2.5);

    const previousLayer = currentLayer;
    currentLayer = null;

    const currentZoom = map.getZoom();

    function _finish() {
      isLoading = false;
      if (_pendingRasterLoad) {
        const p = _pendingRasterLoad;
        _pendingRasterLoad = null;
        window.loadRaster(p.rasterUrl, p.colorscaleUrl, p.date, p.dateRangeObj, p.continent, p.tempType);
      }
    }
    const cacheBuster = '&_cache=' + Date.now();
    const bustRasterUrl = rasterUrl + '&zoom_level=' + currentZoom + cacheBuster;

    const colorscaleReady = skipColorscale
      ? Promise.resolve()
      : fetch(colorscaleUrl + cacheBuster)
          .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}: Failed to fetch colorscale`);
            return r.json();
          })
          .then(meta => {
            if (!meta || !meta.min_value || !meta.max_value) {
              throw new Error('Invalid colorscale response format');
            }
            vmin = meta.min_value;
            vmax = meta.max_value;
            document.getElementById('leg-min').textContent = (vmin - 273.15).toFixed(1) + '°C';
            document.getElementById('leg-max').textContent = (vmax - 273.15).toFixed(1) + '°C';
            document.getElementById('leg-units').textContent = 'Absolute Scale';
            document.getElementById('leg-title').textContent = 'Temperature';
          });

    colorscaleReady
      .then(() => {
        _progressTo(15, 0);
        _progressTo(60, 25);
        if (_barLabel) _barLabel.textContent = 'LOADING RASTER';
        return fetch(bustRasterUrl);
      })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}: Failed to fetch raster`);
        _progressTo(65, 0);
        _progressTo(85, 3.5);
        if (_barLabel) _barLabel.textContent = 'RENDERING';
        return r.arrayBuffer();
      })
      .then(ab => {
        if (!ab || ab.byteLength === 0) throw new Error('Received empty raster data');
        _progressTo(88, 0);
        _progressTo(97, 0.8);
        return parseGeoraster(ab);
      })
      .then(georaster => {
        if (previousLayer) {
          try { map.removeLayer(previousLayer); }
          catch (e) { console.error('Error removing previous layer:', e); }
        }

        currentLayer = new GeoRasterLayer({
          georaster,
          opacity: 0.45,
          pixelValuesToColorFn: values => {
            const v = values[0];
            if (v == null || isNaN(v)) return null;
            return getAbsoluteColor(v);
          },
          resolution: 256,
          updateWhenZooming: false,
        });

        currentLayer.addTo(map);
        if (admin1Layer) admin1Layer.bringToFront();
        if (borderLayer) borderLayer.bringToFront();

        const isInitialLoad = lastFetchedZoomLevel === null;
        if (isInitialLoad) {
          if (continent && continentBounds[continent]) {
            const b = continentBounds[continent].bounds;
            const llBounds = [[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]];
            lastFetchedZoomLevel = map.getBoundsZoom(llBounds);
            map.fitBounds(llBounds);
          } else {
            const bounds = currentLayer.getBounds();
            lastFetchedZoomLevel = map.getBoundsZoom(bounds);
            map.fitBounds(bounds);
          }
        } else {
          lastFetchedZoomLevel = currentZoom;
        }

        rasterUrls.rasterUrl = rasterUrl;
        rasterUrls.colorscaleUrl = colorscaleUrl;
        currentContinent = continent;

        _progressDone();
        _finish();
      })
      .catch(e => {
        console.error('Raster load error:', e);
        _progressError();

        if (previousLayer && !currentLayer) {
          try { currentLayer = previousLayer; map.addLayer(previousLayer); }
          catch (err) { console.error('Could not restore previous layer:', err); }
        }
        _finish();
      });
  };

  // ---------------------------------------------------------------------------
  // Click: fetch cell value and relay coordinate to parent Dash frame
  // ---------------------------------------------------------------------------

  const tooltip = document.getElementById('tooltip');

  map.on('click', function (e) {
    if (!currentDate) {
      console.warn('No date selected. Please render a heatmap first.');
      return;
    }

    let lat = e.latlng.lat;
    let lon = ((e.latlng.lng + 180) % 360) - 180; // normalise to [-180, 180]

    lat = lat.toFixed(4);
    lon = lon.toFixed(4);

    fetch(`${API}/value?date_str=${currentDate}&lat=${lat}&lon=${lon}&temp_type=${currentTempType}`)
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(d => {
        const celsius = (d.value - 273.15).toFixed(2);
        const k = d.value != null ? celsius + ' °C' : '—';
        tooltip.innerHTML =
          `<span class="hi">${currentDate}</span><br>` +
          `<span class="lo">lat ${d.lat}  lon ${d.lon}</span><br>` +
          `<span class="hi">${k}</span>`;
        tooltip.style.display = 'block';

        // Only open the timeseries graph when land data exists at this point
        window.lastClickedCoordinate = {
          lat: parseFloat(lat), lon: parseFloat(lon),
          date: currentDate, dateRange: dateRange,
        };
        window.parent.postMessage({
          type: 'coordinateClicked',
          lat: parseFloat(lat), lon: parseFloat(lon),
          date: currentDate, dateRange: dateRange,
        }, '*');
      })
      .catch(err => {
        console.error('Error fetching value:', err);
        tooltip.style.display = 'none';
      });
  });

  map.on('mouseout', () => { tooltip.style.display = 'none'; });

  // ---------------------------------------------------------------------------
  // Zoom: re-fetch at the right resolution when crossing thresholds
  // ---------------------------------------------------------------------------

  map.on('zoomend', function () {
    // Country borders stay visible at all zooms; provinces fade in at ADMIN1_ZOOM
    if (admin1Layer) {
      if (map.getZoom() >= ADMIN1_ZOOM) {
        admin1Layer.setStyle({ opacity: 1 });
        admin1Layer.bringToFront();
        if (borderLayer) borderLayer.bringToFront();
      } else {
        admin1Layer.setStyle({ opacity: 0 });
      }
    }

    if (!currentDate || !rasterUrls.rasterUrl) return;

    const newZoom = map.getZoom();
    let shouldRefetch = false;

    if (lastFetchedZoomLevel === null) {
      shouldRefetch = true;
    } else if (lastFetchedZoomLevel < 4 && newZoom >= 4) {
      shouldRefetch = true; // was 4x downsampled, now need 2x or full
    } else if (lastFetchedZoomLevel < 8 && newZoom >= 8) {
      shouldRefetch = true; // was 2x downsampled, now need full
    } else if (lastFetchedZoomLevel >= 8 && newZoom < 8) {
      shouldRefetch = true; // zooming out: need coarser resolution
    } else if (lastFetchedZoomLevel >= 4 && newZoom < 4) {
      shouldRefetch = true; // zooming out: need coarsest resolution
    }

    if (shouldRefetch && !isLoading) {
      log('Zoom threshold crossed (' + lastFetchedZoomLevel + ' → ' + newZoom + '): re-fetching');
      window.loadRaster(
        rasterUrls.rasterUrl, rasterUrls.colorscaleUrl,
        currentDate, dateRange, currentContinent, currentTempType,
        true
      );
    }
  });

  // ---------------------------------------------------------------------------
  // postMessage: accept commands from the parent Dash frame
  // ---------------------------------------------------------------------------

  window.addEventListener('message', e => {
    if (e.data && e.data.type === 'progressStart') {
      _progressStart(e.data.label || 'LOADING');
      _progressTo(12, 20);
    }
    if (e.data && e.data.type === 'loadRaster') {
      window.loadRaster(
        e.data.rasterUrl, e.data.colorscaleUrl,
        e.data.date, e.data.dateRange, e.data.continent, e.data.tempType
      );
    }
    if (e.data && e.data.type === 'setView') {
      map.setView(e.data.center, e.data.zoom);
    }
  });
})();
