"""
SIG Server — Plataforma GIS Online
"""
import os
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
    vid = str(uuid.uuid4())[:8]
    vector_name = ''
    main_type = ''
    # Determine name from first recognized file
    for f in files:
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext in ('shp', 'kml', 'kmz', 'gpkg', 'zip'):
            vector_name = f.filename.rsplit('.', 1)[0]
            main_type = ext
            break
    if not vector_name:
        vector_name = files[0].filename.rsplit('.', 1)[0]
    # Save all files
    for f in files:
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        fname = f'{vid}_{secure_filename(f.filename)}'
        f.save(os.path.join(VECTOR_DIR, fname))
    # Update metadata
    meta_path = os.path.join(VECTOR_DIR, f'{project}_groups.json')
    groups = []
    if os.path.isfile(meta_path):
        with open(meta_path) as mf:
            groups = json.load(mf)
    for g in groups:
        if g['id'] == gid:
            g.setdefault('vectors', []).append({'id': vid, 'name': vector_name, 'type': main_type})
            break
    with open(meta_path, 'w') as mf:
        json.dump(groups, mf)
    return jsonify({'success': True, 'id': vid, 'name': vector_name, 'type': main_type})

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
        r = subprocess.run(['ogr2ogr', '-f', 'GeoJSON', '/vsistdout/', main_file],
                          capture_output=True, text=True, timeout=60)
        print(f'ogr2ogr for {vid}: returncode={r.returncode}, stdout_len={len(r.stdout)}, stderr={r.stderr[:200]}')
        if r.returncode == 0 and r.stdout:
            return (r.stdout, 200, {'Content-Type': 'application/geo+json'})
        return jsonify({'error': f'Conversão falhou: {r.stderr[:300]}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
