"""
SIG Server — Plataforma GIS Online
"""
import os
import shutil
import requests as req
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5GB
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'shp', 'shx', 'dbf', 'prj', 'kml', 'kmz', 'gpkg', 'zip'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# In-memory tile cache (max 5000 tiles)
_tile_cache = {}

# Raster storage
RASTER_DIR = os.path.join(os.path.dirname(__file__), 'rasters')
os.makedirs(RASTER_DIR, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/projects', methods=['GET'])
def list_projects():
    uploads = app.config['UPLOAD_FOLDER']
    projects = [d for d in os.listdir(uploads) if os.path.isdir(os.path.join(uploads, d))]
    return jsonify({'projects': projects})

@app.route('/api/projects/<project>/layers', methods=['GET'])
def list_layers(project):
    project_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(project))
    if not os.path.isdir(project_dir):
        return jsonify({'error': 'Projeto não encontrado'}), 404
    files = [f for f in os.listdir(project_dir) if os.path.isfile(os.path.join(project_dir, f))]
    layers = []
    for f in files:
        ext = f.rsplit('.', 1)[1].lower() if '.' in f else ''
        name = f.rsplit('.', 1)[0]
        if ext in ALLOWED_EXTENSIONS:
            layers.append({'name': name, 'filename': f, 'type': ext})
    return jsonify({'layers': layers})

@app.route('/api/projects/<project>/upload', methods=['POST'])
def upload_file(project):
    project_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(project))
    os.makedirs(project_dir, exist_ok=True)
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nome vazio'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Tipo não permitido'}), 400
    filename = secure_filename(file.filename)
    file.save(os.path.join(project_dir, filename))
    return jsonify({'success': True, 'filename': filename})

@app.route('/api/projects/<project>/file/<filename>', methods=['GET'])
def get_file(project, filename):
    project_dir = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(project))
    filepath = os.path.join(project_dir, secure_filename(filename))
    if not os.path.isfile(filepath):
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext == 'kml':
        return send_from_directory(project_dir, secure_filename(filename), mimetype='application/vnd.google-earth.kml+xml')
    elif ext == 'geojson':
        return send_from_directory(project_dir, secure_filename(filename), mimetype='application/geo+json')
    return send_from_directory(project_dir, secure_filename(filename))

@app.route('/api/wayback-tile/<wb_id>/<wb_m>/<int:z>/<int:y>/<int:x>', methods=['GET'])
def wayback_tile(wb_id, wb_m, z, y, x):
    cache_key = f"{wb_id}_{wb_m}_{z}_{y}_{x}"
    if cache_key in _tile_cache:
        data, ctype = _tile_cache[cache_key]
        return (data, 200, {'Content-Type': ctype, 'Cache-Control': 'public, max-age=604800', 'X-Cache': 'HIT'})
    url = f'https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/{wb_id}/MapServer/tile/{wb_m}/{z}/{y}/{x}'
    try:
        r = req.get(url, timeout=8)
        ctype = r.headers.get('Content-Type', 'image/jpeg')
        if len(_tile_cache) > 5000:
            _tile_cache.clear()
        _tile_cache[cache_key] = (r.content, ctype)
        return (r.content, 200, {'Content-Type': ctype, 'Cache-Control': 'public, max-age=604800', 'X-Cache': 'MISS'})
    except:
        return ('', 404)

@app.route('/api/upload-raster', methods=['POST'])
def upload_raster():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo'}), 400
    f = request.files['file']
    if not f.filename.lower().endswith(('.tif', '.tiff')):
        return jsonify({'error': 'Apenas .tif'}), 400
    project = request.form.get('project', 'default')
    # Use timestamp-based ID to support multiple rasters
    import time, uuid
    rid = str(uuid.uuid4())[:8]
    filename = f'{project}_{rid}_raster.tif'
    src = os.path.join(RASTER_DIR, filename)
    f.save(src)
    # Extract bounds and CRS, transform to WGS84
    bounds = None
    try:
        import subprocess, json
        r = subprocess.run(['gdalinfo', '-json', src], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            info = json.loads(r.stdout)
            corners = info.get('cornerCoordinates', {})
            wgs_bounds = info.get('wgs84Extent', None)
            if wgs_bounds and isinstance(wgs_bounds, dict):
                coords = wgs_bounds.get('coordinates', [[]])[0]
                if len(coords) >= 4:
                    # [[minX,minY],[minX,maxY],[maxX,maxY],[maxX,minY],[minX,minY]]
                    bounds = [[coords[0][1], coords[0][0]], [coords[2][1], coords[2][0]]]
            if not bounds and corners:
                ll = corners.get('lowerLeft', [0,0])
                ur = corners.get('upperRight', [0,0])
                # Check if CRS is not WGS84 — transform with pyproj
                srs = info.get('spatialReference', {})
                epsg = None
                if srs:
                    # Try to extract EPSG code
                    auth = srs.get('authority', '')
                    if 'EPSG' in str(srs):
                        import re
                        m = re.search(r'EPSG[:\s]*(\d+)', str(srs))
                        if m: epsg = int(m.group(1))
                if epsg and epsg != 4326:
                    from pyproj import Transformer
                    t = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True)
                    ll_wgs = t.transform(ll[0], ll[1])
                    ur_wgs = t.transform(ur[0], ur[1])
                    bounds = [[ll_wgs[1], ll_wgs[0]], [ur_wgs[1], ur_wgs[0]]]
                else:
                    bounds = [[ll[1], ll[0]], [ur[1], ur[0]]]
    except Exception as e:
        print(f'Bounds extraction error: {e}')
    if not bounds:
        try:
            from PIL import Image
            img = Image.open(src)
            if hasattr(img, 'tag_v2'):
                tags = img.tag_v2
                if 33922 in tags and 33550 in tags:
                    tp = tags[33922]
                    ps = tags[33550]
                    x_size, y_size = img.size
                    # Raw bounds in native CRS
                    minx, maxy = tp[3], tp[4]
                    maxx = minx + x_size * ps[0]
                    miny = maxy - y_size * ps[1]
                    # Try to find EPSG from tags
                    epsg = None
                    if 34735 in tags:
                        wkt = tags[34735]
                        if isinstance(wkt, (list, tuple)):
                            wkt = ''.join(chr(c) for c in wkt)
                        if 'UTM' in str(wkt):
                            import re
                            m = re.search(r'(\d{6})', str(wkt))
                            if m:
                                zone = int(m.group(1))
                                if zone > 3000:
                                    epsg = 32700 + (zone - 300000) // 100  # UTM South
                                else:
                                    epsg = 32600 + zone // 100  # UTM North
                        m = re.search(r'EPSG.*?(\d{4,6})', str(wkt))
                        if m: epsg = int(m.group(1))
                    if epsg and epsg != 4326:
                        from pyproj import Transformer
                        t = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True)
                        ll_wgs = t.transform(minx, miny)
                        ur_wgs = t.transform(maxx, maxy)
                        bounds = [[ll_wgs[1], ll_wgs[0]], [ur_wgs[1], ur_wgs[0]]]
                    else:
                        bounds = [[miny, minx], [maxy, maxx]]
        except Exception as e:
            print(f'Pillow bounds error: {e}')
    # Convert to PNG
    png_path = os.path.join(RASTER_DIR, f'{project}_{rid}_raster.png')
    converted = False
    try:
        import subprocess
        r = subprocess.run(['gdal_translate', '-of', 'PNG', '-scale', '-outsize', '4096', '4096', src, png_path],
                          capture_output=True, timeout=180)
        converted = r.returncode == 0 and os.path.isfile(png_path)
    except Exception:
        pass
    if not converted:
        try:
            from PIL import Image, ImageOps
            img = Image.open(src)
            if img.mode not in ('RGB', 'RGBA'):
                bands = img.getbands()
                if len(bands) >= 3:
                    img = Image.merge('RGB', (img.getchannel(bands[0]), img.getchannel(bands[1]), img.getchannel(bands[2])))
                else:
                    img = img.convert('RGB')
            img = ImageOps.autocontrast(img, cutoff=1)
            img.thumbnail((4096, 4096), Image.LANCZOS)
            img.save(png_path, 'PNG')
            converted = True
        except Exception as e:
            print(f'PNG conversion error: {e}')
    # Store metadata
    import json
    meta_path = os.path.join(RASTER_DIR, f'{project}_meta.json')
    metas = []
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            metas = json.load(mf)
    display_name = secure_filename(f.filename).rsplit('.', 1)[0]
    metas.append({'id': rid, 'name': display_name, 'bounds': bounds, 'has_png': converted})
    with open(meta_path, 'w') as mf:
        json.dump(metas, mf)
    print(f'Raster uploaded: {display_name} ({rid}), bounds={bounds}')
    return jsonify({'success': True, 'id': rid, 'name': display_name, 'bounds': bounds, 'has_png': converted})

@app.route('/api/rasters/<project>', methods=['GET'])
def list_rasters(project):
    import json
    meta_path = os.path.join(RASTER_DIR, f'{project}_meta.json')
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            return jsonify(json.load(mf))
    return jsonify([])

@app.route('/api/raster/<project>/<rid>', methods=['GET'])
def get_raster(project, rid):
    png_path = os.path.join(RASTER_DIR, f'{project}_{rid}_raster.png')
    if os.path.isfile(png_path):
        return send_from_directory(RASTER_DIR, f'{project}_{rid}_raster.png', mimetype='image/png')
    tif_path = os.path.join(RASTER_DIR, f'{project}_{rid}_raster.tif')
    if os.path.isfile(tif_path):
        return send_from_directory(RASTER_DIR, f'{project}_{rid}_raster.tif', mimetype='image/tiff')
    return jsonify({'error': 'Raster não encontrado'}), 404

@app.route('/api/raster/<project>/<rid>', methods=['DELETE'])
def delete_raster(project, rid):
    import json, shutil
    for ext in ['tif', 'png']:
        p = os.path.join(RASTER_DIR, f'{project}_{rid}_raster.{ext}')
        if os.path.isfile(p): os.remove(p)
    meta_path = os.path.join(RASTER_DIR, f'{project}_meta.json')
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            metas = json.load(mf)
        metas = [m for m in metas if m['id'] != rid]
        with open(meta_path, 'w') as mf:
            json.dump(metas, mf)
    return jsonify({'success': True})

# ===== RASTER GROUPS =====
@app.route('/api/raster-groups/<project>', methods=['GET'])
def list_raster_groups(project):
    import json
    p = os.path.join(RASTER_DIR, f'{project}_rgroups.json')
    if os.path.isfile(p):
        with open(p) as f: return jsonify(json.load(f))
    return jsonify([])

@app.route('/api/raster-groups/<project>', methods=['POST'])
def save_raster_groups(project):
    import json
    data = request.get_json() or []
    p = os.path.join(RASTER_DIR, f'{project}_rgroups.json')
    with open(p, 'w') as f: json.dump(data, f)
    return jsonify({'success': True})

@app.route('/api/raster-groups/<project>/group', methods=['POST'])
def create_raster_group(project):
    import json, uuid
    data = request.get_json() or {}
    name = data.get('name', 'Novo Grupo')
    p = os.path.join(RASTER_DIR, f'{project}_rgroups.json')
    groups = []
    if os.path.isfile(p):
        with open(p) as f: groups = json.load(f)
    gid = str(uuid.uuid4())[:8]
    groups.append({'id': gid, 'name': name, 'rasters': []})
    with open(p, 'w') as f: json.dump(groups, f)
    return jsonify({'success': True, 'id': gid})

@app.route('/api/raster-groups/<project>/group/<gid>', methods=['PUT'])
def rename_raster_group(project, gid):
    import json
    data = request.get_json() or {}
    p = os.path.join(RASTER_DIR, f'{project}_rgroups.json')
    if os.path.isfile(p):
        with open(p) as f: groups = json.load(f)
        for g in groups:
            if g['id'] == gid:
                g['name'] = data.get('name', g['name']); break
        with open(p, 'w') as f: json.dump(groups, f)
    return jsonify({'success': True})

@app.route('/api/raster-groups/<project>/group/<gid>', methods=['DELETE'])
def delete_raster_group(project, gid):
    import json
    p = os.path.join(RASTER_DIR, f'{project}_rgroups.json')
    if os.path.isfile(p):
        with open(p) as f: groups = json.load(f)
        for g in groups:
            if g['id'] == gid:
                for r in g.get('rasters', []):
                    for ext in ['tif', 'png']:
                        fp = os.path.join(RASTER_DIR, f'{project}_{r["id"]}_raster.{ext}')
                        if os.path.isfile(fp): os.remove(fp)
                break
        groups = [g for g in groups if g['id'] != gid]
        with open(p, 'w') as f: json.dump(groups, f)
    return jsonify({'success': True})

@app.route('/api/raster-groups/<project>/group/<gid>/upload', methods=['POST'])
def upload_raster_to_group(project, gid):
    import json, uuid, subprocess
    files = request.files.getlist('file')
    if not files: return jsonify({'error': 'Nenhum arquivo'}), 400
    p = os.path.join(RASTER_DIR, f'{project}_rgroups.json')
    groups = []
    if os.path.isfile(p):
        with open(p) as f: groups = json.load(f)
    all_bounds = []
    results = []
    for file in files:
        if not file.filename.lower().endswith(('.tif', '.tiff')): continue
        rid = str(uuid.uuid4())[:8]
        fname = f'{project}_{rid}_raster.tif'
        tif_path = os.path.join(RASTER_DIR, fname)
        file.save(tif_path)
        # Get bounds
        bounds = None
        try:
            r = subprocess.run(['gdalinfo', '-json', tif_path], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                info = json.loads(r.stdout)
                corners = [c for c in info.get('cornerCoordinates', {}).values() if isinstance(c, dict) and 'x' in c]
                if corners:
                    lons = [c['x'] for c in corners]; lats = [c['y'] for c in corners]
                    bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]
        except: pass
        if not bounds:
            try:
                from PIL import Image
                img = Image.open(tif_path)
                bounds = [[-90, -180], [90, 180]]
                img.close()
            except: pass
        name = file.filename.rsplit('.', 1)[0]
        raster_info = {'id': rid, 'name': name}
        if bounds: raster_info['bounds'] = bounds
        results.append(raster_info)
        if bounds: all_bounds.extend(bounds)
    for g in groups:
        if g['id'] == gid:
            g.setdefault('rasters', []).extend(results)
            break
    with open(p, 'w') as f: json.dump(groups, f)
    resp = {'success': True, 'rasters': results}
    if all_bounds:
        lons = [b[0][1] for b in all_bounds] + [b[1][1] for b in all_bounds]
        lats = [b[0][0] for b in all_bounds] + [b[1][0] for b in all_bounds]
        resp['bounds'] = [[min(lats), min(lons)], [max(lats), max(lons)]]
    return jsonify(resp)

@app.route('/api/raster-groups/<project>/group/<gid>/raster/<rid>', methods=['DELETE'])
def delete_raster_from_group(project, gid, rid):
    import json
    for ext in ['tif', 'png']:
        fp = os.path.join(RASTER_DIR, f'{project}_{rid}_raster.{ext}')
        if os.path.isfile(fp): os.remove(fp)
    p = os.path.join(RASTER_DIR, f'{project}_rgroups.json')
    if os.path.isfile(p):
        with open(p) as f: groups = json.load(f)
        for g in groups:
            if g['id'] == gid:
                g['rasters'] = [r for r in g.get('rasters', []) if r['id'] != rid]; break
        with open(p, 'w') as f: json.dump(groups, f)
    return jsonify({'success': True})

# ===== VECTOR GROUPS =====
VECTOR_DIR = os.path.join(os.path.dirname(__file__), 'vectors')
os.makedirs(VECTOR_DIR, exist_ok=True)

@app.route('/api/vector/<project>/groups', methods=['GET'])
def list_vector_groups(project):
    import json
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            return jsonify(json.load(mf))
    return jsonify([])

@app.route('/api/vector/<project>/groups', methods=['POST'])
def save_vector_groups(project):
    import json
    data = request.get_json() or []
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    with open(meta_path, 'w') as mf:
        json.dump(data, mf)
    return jsonify({'success': True})

@app.route('/api/vector/<project>/group', methods=['POST'])
def create_vector_group(project):
    import json, uuid
    data = request.get_json() or {}
    name = data.get('name', 'Novo Grupo')
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    groups = []
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            groups = json.load(mf)
    gid = str(uuid.uuid4())[:8]
    groups.append({'id': gid, 'name': name, 'vectors': []})
    with open(meta_path, 'w') as mf:
        json.dump(groups, mf)
    return jsonify({'success': True, 'id': gid, 'name': name})

@app.route('/api/vector/<project>/groups/<gid>', methods=['PUT'])
def rename_vector_group(project, gid):
    import json
    data = request.get_json() or {}
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            groups = json.load(mf)
        for g in groups:
            if g['id'] == gid:
                g['name'] = data.get('name', g['name'])
                break
        with open(meta_path, 'w') as mf:
            json.dump(groups, mf)
    return jsonify({'success': True})

@app.route('/api/vector/<project>/groups/<gid>', methods=['DELETE'])
def delete_vector_group(project, gid):
    import json, shutil
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            groups = json.load(mf)
        for g in groups:
            if g['id'] == gid:
                for v in g.get('vectors', []):
                    for old in os.listdir(VECTOR_DIR):
                        if old.startswith(f'{v["id"]}_'):
                            os.remove(os.path.join(VECTOR_DIR, old))
                break
        groups = [g for g in groups if g['id'] != gid]
        with open(meta_path, 'w') as mf:
            json.dump(groups, mf)
    return jsonify({'success': True})

@app.route('/api/vector/<project>/groups/<gid>/upload', methods=['POST'])
def upload_vector(project, gid):
    import json, uuid
    files = request.files.getlist('file')
    if not files:
        return jsonify({'error': 'Nenhum arquivo'}), 400
    # Group files by base name (shapefile sets)
    file_groups = {}
    standalone = []
    for f in files:
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext in ('shp', 'shx', 'dbf', 'prj', 'cpg', 'sbx', 'sbn', 'prj'):
            base = f.filename.rsplit('.', 1)[0]
            file_groups.setdefault(base, []).append(f)
        elif ext in ('kml', 'kmz', 'gpkg', 'zip'):
            standalone.append(f)
        else:
            standalone.append(f)
    # Process each shapefile group as one vector
    results = []
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    groups = []
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            groups = json.load(mf)
    for base, fgroup in file_groups.items():
        vid = str(uuid.uuid4())[:8]
        for f in fgroup:
            fname = f'{vid}_{secure_filename(f.filename)}'
            f.save(os.path.join(VECTOR_DIR, fname))
        for g in groups:
            if g['id'] == gid:
                g.setdefault('vectors', []).append({'id': vid, 'name': base, 'type': 'shp'})
                break
        results.append({'id': vid, 'name': base, 'type': 'shp'})
    for f in standalone:
        vid = str(uuid.uuid4())[:8]
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        name = f.filename.rsplit('.', 1)[0]
        if ext == 'zip':
            name = name.rsplit('.', 1)[0] if '.' in name else name
        fname = f'{vid}_{secure_filename(f.filename)}'
        f.save(os.path.join(VECTOR_DIR, fname))

        # For GeoPackage: convert each layer to shapefile
        if ext == 'gpkg':
            import subprocess as sp, re, tempfile
            gpkg_path = os.path.join(VECTOR_DIR, fname)
            try:
                r = sp.run(['ogrinfo', gpkg_path], capture_output=True, text=True, timeout=30)
                app.logger.info(f'GPKG ogrinfo: rc={r.returncode} stdout={r.stdout[:500]} stderr={r.stderr[:200]}')
                if r.returncode == 0:
                    gpkg_layers = []
                    for line in r.stdout.split('\n'):
                        m = re.match(r'^(\d+):\s+(\S+)', line.strip())
                        if m:
                            layer_name = m.group(2).strip('(')
                            if layer_name and layer_name not in gpkg_layers:
                                gpkg_layers.append(layer_name)
                    if not gpkg_layers:
                        gpkg_layers = [None]
                    app.logger.info(f'GPKG layers: {gpkg_layers}')
                    gpkg_entries = []
                    for layer_name in gpkg_layers:
                        layer_vid = str(uuid.uuid4())[:8]
                        layer_display = layer_name if layer_name else name
                        out_dir = tempfile.mkdtemp()
                        out_shp = os.path.join(out_dir, f'{layer_vid}.shp')
                        cmd = ['ogr2ogr', '-f', 'ESRI Shapefile', out_shp, gpkg_path]
                        if layer_name:
                            cmd.append(layer_name)
                            # Sanitize layer name for shapefile (no spaces)
                            safe_name = layer_name.replace(' ', '_').replace('-', '_')
                            cmd.extend(['-nln', safe_name])
                        cr = sp.run(cmd, capture_output=True, text=True, timeout=60)
                        app.logger.info(f'GPKG convert {layer_name}: rc={cr.returncode} shp_exists={os.path.exists(out_shp)} stderr={cr.stderr[:300]}')
                        if cr.returncode != 0 or not os.path.exists(out_shp):
                            continue
                        for ff in os.listdir(out_dir):
                            if ff.startswith(layer_vid):
                                dest = os.path.join(VECTOR_DIR, ff)
                                shutil.copy2(os.path.join(out_dir, ff), dest)
                        shutil.rmtree(out_dir, ignore_errors=True)
                        # Verify files were created
                        created = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f'{layer_vid}_')]
                        app.logger.info(f'GPKG layer {layer_name}: vid={layer_vid} files={created}')
                        if not created:
                            continue
                        layer_display = layer_name if layer_name else name
                        gpkg_entries.append({'id': layer_vid, 'name': f"{name}_{layer_display}"})
                    if gpkg_entries:
                        for entry in gpkg_entries:
                            for g in groups:
                                if g['id'] == gid:
                                    g.setdefault('vectors', []).append({'id': entry['id'], 'name': entry['name'], 'type': 'shp'})
                                    break
                            results.append({'id': entry['id'], 'name': entry['name'], 'type': 'shp'})
                        with open(meta_path, 'w') as mf:
                            json.dump(groups, mf)
                        os.remove(gpkg_path)
                        continue
            except Exception as e:
                app.logger.error(f'GPKG conversion error: {e}')
            # Fallback: treat as single GPKG vector
            for g in groups:
                if g['id'] == gid:
                    g.setdefault('vectors', []).append({'id': vid, 'name': name, 'type': 'gpkg'})
                    break
            results.append({'id': vid, 'name': name, 'type': 'gpkg'})
            with open(meta_path, 'w') as mf:
                json.dump(groups, mf)
            continue

        for g in groups:
            if g['id'] == gid:
                g.setdefault('vectors', []).append({'id': vid, 'name': name, 'type': ext})
                break
        results.append({'id': vid, 'name': name, 'type': ext})
    with open(meta_path, 'w') as mf:
        json.dump(groups, mf)
    return jsonify({'success': True, 'vectors': results})

@app.route('/api/vector/<project>/download/<vid>', methods=['GET'])
def download_vector(project, vid):
    """Download a single vector as zip with all its files."""
    import zipfile, io
    files = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f'{vid}_')]
    if not files:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    # Find vector name from groups metadata
    import json
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    vec_name = vid
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            groups = json.load(mf)
        for g in groups:
            for v in g.get('vectors', []):
                if v['id'] == vid:
                    vec_name = secure_filename(v.get('name', vid))
                    break
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            # Strip vid_ prefix from filename
            clean_name = f[len(vid)+1:]
            zf.write(os.path.join(VECTOR_DIR, f), clean_name)
    buf.seek(0)
    return (buf.getvalue(), 200, {
        'Content-Type': 'application/zip',
        'Content-Disposition': f'attachment; filename="{vec_name}.zip"'
    })

@app.route('/api/vector/<project>/groups/<gid>/download', methods=['GET'])
def download_vector_group(project, gid):
    """Download all vectors in a group as zip organized in folders."""
    import zipfile, io, json
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    if not os.path.isfile(meta_path):
        return jsonify({'error': 'Grupo não encontrado'}), 404
    with open(meta_path) as mf:
        groups = json.load(mf)
    group = next((g for g in groups if g['id'] == gid), None)
    if not group:
        return jsonify({'error': 'Grupo não encontrado'}), 404
    buf = io.BytesIO()
    group_name = secure_filename(group.get('name', gid))
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for vec in group.get('vectors', []):
            files = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f"{vec['id']}_")]
            vec_name = secure_filename(vec.get('name', vec['id']))
            for f in files:
                clean_name = f[len(vec['id'])+1:]
                zf.write(os.path.join(VECTOR_DIR, f), f"{group_name}/{vec_name}/{clean_name}")
    buf.seek(0)
    return (buf.getvalue(), 200, {
        'Content-Type': 'application/zip',
        'Content-Disposition': f'attachment; filename="{group_name}.zip"'
    })

@app.route('/api/vector/<project>/geojson/<vid>/columns', methods=['GET'])
def get_vector_columns(project, vid):
    """Convert vector to GeoJSON on-the-fly and return property columns with unique values."""
    import json, subprocess, zipfile, tempfile
    files = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f'{vid}_')]
    if not files:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    main_file = None
    for f in files:
        if f.endswith('.zip'):
            main_file = os.path.join(VECTOR_DIR, f)
            break
    if not main_file:
        for f in files:
            ext = f.rsplit('.', 1)[-1].lower()
            if ext in ('shp', 'gpkg', 'kml', 'geojson'):
                main_file = os.path.join(VECTOR_DIR, f)
                break
    if not main_file:
        return jsonify({'error': 'Formato não suportado'}), 400
    try:
        if main_file.endswith('.zip'):
            tmpdir = tempfile.mkdtemp()
            with zipfile.ZipFile(main_file, 'r') as z:
                z.extractall(tmpdir)
            for f in os.listdir(tmpdir):
                ext = f.rsplit('.', 1)[-1].lower()
                if ext in ('shp', 'gpkg', 'kml'):
                    main_file = os.path.join(tmpdir, f)
                    break
        layer_name = request.args.get('layer')
        ogr_cmd = ['ogr2ogr', '-f', 'GeoJSON', '-t_srs', 'EPSG:4326', '/vsistdout/']
        if layer_name and main_file.endswith('.gpkg'):
            ogr_cmd.append(main_file)
            ogr_cmd.append(layer_name)
        else:
            ogr_cmd.append(main_file)
        r = subprocess.run(ogr_cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not r.stdout:
            return jsonify({'error': f'Conversão falhou: {r.stderr[:300]}'}), 500
        gj = json.loads(r.stdout)
        columns = {}
        for feat in gj.get('features', []):
            props = feat.get('properties', {})
            for k, v in props.items():
                if v is None or isinstance(v, (dict, list)):
                    continue
                if k not in columns:
                    columns[k] = set()
                columns[k].add(str(v))
        result = []
        for k, vals in columns.items():
            result.append({'name': k, 'values': sorted(vals), 'count': len(vals)})
        return jsonify({'columns': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vector/<project>/groups/<gid>/vector/<vid>', methods=['DELETE'])
def delete_vector(project, gid, vid):
    import json
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            groups = json.load(mf)
        for g in groups:
            if g['id'] == gid:
                for v in g.get('vectors', []):
                    if v['id'] == vid:
                        for old in os.listdir(VECTOR_DIR):
                            if old.startswith(f'{vid}_'):
                                os.remove(os.path.join(VECTOR_DIR, old))
                        g['vectors'] = [vv for vv in g['vectors'] if vv['id'] != vid]
                        break
        with open(meta_path, 'w') as mf:
            json.dump(groups, mf)
    return jsonify({'success': True})

@app.route('/api/vector/<project>/file/<filename>', methods=['GET'])
def get_vector_file(project, filename):
    path = os.path.join(VECTOR_DIR, secure_filename(filename))
    if os.path.isfile(path):
        return send_from_directory(VECTOR_DIR, secure_filename(filename))
    return jsonify({'error': 'Arquivo não encontrado'}), 404

@app.route('/api/vector/<project>/files/<vid>', methods=['GET'])
def get_vector_files_list(project, vid):
    """List all files for a vector"""
    files = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f'{vid}_')]
    return jsonify({'files': files})

@app.route('/api/vector/<project>/detect-type/<vid>', methods=['GET'])
def detect_vector_type(project, vid):
    """Detect geometry type without full conversion"""
    import subprocess
    layer_name = request.args.get('layer')
    files = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f'{vid}_')]
    main_file = None
    for f in files:
        if f.endswith('.zip'):
            import zipfile, tempfile
            tmpdir = tempfile.mkdtemp()
            with zipfile.ZipFile(os.path.join(VECTOR_DIR, f), 'r') as z:
                z.extractall(tmpdir)
            for ff in os.listdir(tmpdir):
                ext = ff.rsplit('.', 1)[-1].lower()
                if ext in ('shp', 'gpkg', 'kml'):
                    main_file = os.path.join(tmpdir, ff)
                    break
            break
    if not main_file:
        for f in files:
            ext = f.rsplit('.', 1)[-1].lower()
            if ext in ('shp', 'gpkg', 'kml'):
                main_file = os.path.join(VECTOR_DIR, f)
                break
    if not main_file:
        return jsonify({'type': 'polygon'})
    try:
        cmd = ['ogrinfo', '-so', '-al', main_file]
        if layer_name and main_file.endswith('.gpkg'):
            cmd.append(layer_name)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = r.stdout.lower()
        # For GPKG with specific layer, check the layer's geometry section
        if layer_name and main_file.endswith('.gpkg'):
            # ogrinfo -al with layer shows only that layer's info
            if 'point' in output and 'polygon' not in output and 'line' not in output:
                return jsonify({'type': 'point'})
            elif 'line string' in output or 'linestring' in output or 'multiline' in output:
                return jsonify({'type': 'line'})
            elif 'polygon' in output or 'multipolygon' in output:
                return jsonify({'type': 'polygon'})
        else:
            if 'point' in output:
                return jsonify({'type': 'point'})
            elif 'line string' in output or 'linestring' in output or 'multiline' in output:
                return jsonify({'type': 'line'})
            elif 'polygon' in output or 'multipolygon' in output:
                return jsonify({'type': 'polygon'})
        return jsonify({'type': 'polygon'})
    except:
        return jsonify({'type': 'polygon'})

@app.route('/api/vector/<project>/geojson/<vid>', methods=['GET'])
def get_vector_geojson(project, vid):
    """Convert shapefile/gpkg to GeoJSON using ogr2ogr"""
    import subprocess, json, zipfile, tempfile
    files = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f'{vid}_')]
    if not files:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    main_file = None
    # Check for zip first
    for f in files:
        if f.endswith('.zip'):
            main_file = os.path.join(VECTOR_DIR, f)
            break
    if not main_file:
        for f in files:
            ext = f.rsplit('.', 1)[-1].lower()
            if ext in ('shp', 'gpkg', 'kml', 'geojson'):
                main_file = os.path.join(VECTOR_DIR, f)
                break
    if not main_file:
        return jsonify({'error': 'Formato não suportado'}), 400
    try:
        # If zip, extract to temp dir first
        if main_file.endswith('.zip'):
            tmpdir = tempfile.mkdtemp()
            with zipfile.ZipFile(main_file, 'r') as z:
                z.extractall(tmpdir)
            # Find shp or gpkg inside
            for f in os.listdir(tmpdir):
                ext = f.rsplit('.', 1)[-1].lower()
                if ext in ('shp', 'gpkg', 'kml'):
                    main_file = os.path.join(tmpdir, f)
                    break
        # For GeoPackage, support layer selection via query param
        ogr_cmd = ['ogr2ogr', '-f', 'GeoJSON', '-t_srs', 'EPSG:4326', '/vsistdout/', main_file]
        if main_file.endswith('.gpkg'):
            layer_name = request.args.get('layer')
            if layer_name:
                ogr_cmd = ['ogr2ogr', '-f', 'GeoJSON', '-t_srs', 'EPSG:4326', '/vsistdout/', main_file, layer_name]
        r = subprocess.run(ogr_cmd, capture_output=True, text=True, timeout=60)
        print(f'ogr2ogr for {vid}: returncode={r.returncode}, stdout_len={len(r.stdout)}, stderr={r.stderr[:200]}')
        if r.returncode == 0 and r.stdout:
            return (r.stdout, 200, {'Content-Type': 'application/geo+json'})
        return jsonify({'error': f'Conversão falhou: {r.stderr[:300]}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vector/<project>/geojson/<vid>/layers', methods=['GET'])
def list_gpkg_layers(project, vid):
    """List layers inside a GeoPackage file."""
    import subprocess, json
    files = [f for f in os.listdir(VECTOR_DIR) if f.startswith(f'{vid}_')]
    main_file = None
    for f in files:
        ext = f.rsplit('.', 1)[-1].lower()
        if ext == 'gpkg':
            main_file = os.path.join(VECTOR_DIR, f)
            break
    if not main_file:
        return jsonify({'layers': [], 'is_gpkg': False})
    try:
        r = subprocess.run(['ogrinfo', main_file], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return jsonify({'layers': [], 'is_gpkg': False})
        # Parse layer names from ogrinfo output
        layers = []
        import re
        for line in r.stdout.split('\n'):
            m = re.match(r'^(\d+):\s+(\S+)', line.strip())
            if m:
                layer_name = m.group(2).strip('(')
                if layer_name: layers.append(layer_name)
        return jsonify({'layers': layers, 'is_gpkg': True})
    except:
        return jsonify({'layers': [], 'is_gpkg': False})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
