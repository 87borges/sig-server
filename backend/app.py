"""
SIG Server — Plataforma GIS Online
"""
import os
import requests as req
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
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
    if not f.filename.lower().endswith(('.tif', '.tiff', '.png', '.jpg', '.jpeg')):
        return jsonify({'error': 'Apenas .tif, .png ou .jpg'}), 400
    project = request.form.get('project', 'default')
    for old in os.listdir(RASTER_DIR):
        if old.startswith(f'{project}_raster.'):
            os.remove(os.path.join(RASTER_DIR, old))
    ext = f.filename.rsplit('.', 1)[1].lower()
    filename = f'{project}_raster.{ext}'
    f.save(os.path.join(RASTER_DIR, filename))
    return jsonify({'success': True, 'filename': filename})

@app.route('/api/raster/<project>', methods=['GET'])
def get_raster(project):
    for ext in ['tif', 'tiff', 'png', 'jpg', 'jpeg']:
        path = os.path.join(RASTER_DIR, f'{project}_raster.{ext}')
        if os.path.isfile(path):
            return send_from_directory(RASTER_DIR, f'{project}_raster.{ext}')
    return jsonify({'error': 'Raster não encontrado'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
