# main.py — Meteor Impact (PyQt6, no WebEngine)
import sys, math, requests
from PyQt6 import QtCore, QtGui, QtWidgets

NASA_NEO_BASE = "https://api.nasa.gov/neo/rest/v1"

# ============== Physics / Effects ==============
def volume_sphere(d_m: float) -> float:
    return 4/3 * math.pi * (d_m/2)**3

def mass_from_diameter(d_m: float, rho: float = 3000.0) -> float:
    return rho * volume_sphere(d_m)

def kinetic_energy_joules(m_kg: float, v_km_s: float) -> float:
    return 0.5 * m_kg * (v_km_s*1000.0)**2

def joules_to_megatons_tnt(E_j: float) -> float:
    return E_j / 4.184e15

def surface_yield_mt(kinetic_mt: float, angle_deg: float) -> float:
    theta = max(1.0, min(90.0, angle_deg))
    f = 0.55 + 0.5 * math.sin(math.radians(theta))  # 0.55..~1.05
    return max(kinetic_mt * min(f, 1.0), 1e-9)

def scaled_radius_km(yield_mt: float, k: float) -> float:
    return k * (max(yield_mt, 1e-12) ** (1/3))

def blast_radii_km(yield_mt_surface: float) -> dict:
    return {
        "severe_blast_km":   scaled_radius_km(yield_mt_surface, 1.1),
        "moderate_blast_km": scaled_radius_km(yield_mt_surface, 2.2),
        "light_blast_km":    scaled_radius_km(yield_mt_surface, 3.8),
    }

def thermal_radii_km(yield_mt_surface: float) -> dict:
    return {
        "severe_thermal_km": scaled_radius_km(yield_mt_surface, 1.6),
        "light_thermal_km":  scaled_radius_km(yield_mt_surface, 4.5),
    }

def impact_effects(yield_mt_kinetic: float, angle_deg: float) -> dict:
    Y = surface_yield_mt(yield_mt_kinetic, angle_deg)
    out = {"effective_surface_yield_mt": Y}
    out.update(blast_radii_km(Y))
    out.update(thermal_radii_km(Y))
    return out
# ============== Mitigation helper logic ==============
def classify_size(d_m: float) -> str:
    if d_m < 10: return "<10m"
    if d_m < 50: return "10-50m"
    if d_m < 140: return "50-140m"
    if d_m < 300: return "140-300m"
    if d_m < 1000: return "300m-1km"
    return ">1km"

def guess_event_type(d_m: float, angle_deg: float) -> str:
    if d_m < 60 and angle_deg < 40: 
        return "airburst"
    if d_m < 30: 
        return "airburst"
    return "ground"

def mitigation_brief(size_class: str, event_type: str, lead_years: float, ocean: bool) -> list[str]:
    """
    Возвращает список кратких советов по смягчению последствий, 
    учитывая размер, тип события, lead time и океаничность.
    """
    # базовые блоки по размеру
    base = {
        "<10m": [
            "Public alert within city: do NOT look at the flash; expect shock wave in 1–3 minutes.",
            "Keep people away from windows; cancel ‘go watch the sky’ routines.",
            "Fire service on standby; monitor infrasound/cameras for altitude and yield."
        ],
        "10-50m": [
            "Targeted alerts for light–moderate overpressure zone; move people indoors away from glass.",
            "Pause traffic on bridges/viaducts within forecasted focus area.",
            "Close fuel handling and reduce ignition sources; fire brigades staged."
        ],
        "50-140m": [
            "With ≥5–10 years: kinetic impactor mission; pre-flyby to measure density/shape/rotation.",
            "With days–weeks: staged evacuation from severe/moderate blast zones; firebreak prep.",
            "Shut down hazardous industry; isolate gas lines; protect hospitals’ backup power."
        ],
        "140-300m": [
            "With ≥10 years: series of kinetic impactors; for rubble piles use multi-hit phasing.",
            "Late detection: consider nuclear standoff in deep space (politically hard).",
            "Regional evacuation; protect critical infrastructure and water supplies."
        ],
        "300m-1km": [
            "International mission: multiple impactors; optional standoff; decade-scale navigation.",
            "Inter-regional evacuation planning; energy/communications continuity plans."
        ],
        ">1km": [
            "Only early detection + multi-stage deflection over decades will work.",
            "Global civil-protection planning: food, logistics, medical, climate impacts."
        ],
    }

    # уточнения по типу события
    airburst_tweaks = [
        "Aim to increase burst altitude (if any standoff is possible) to spread the shock.",
        "Prioritize glass hazard mitigation; shelter-in-place beats road evacuation."
    ]
    ground_tweaks = [
        "Crater-forming impact: prioritize full evacuation from severe/moderate blast and thermal zones.",
        "Debris fires likely; wide firebreaks, water resources pre-positioned."
    ]

    # океан
    ocean_block = [
        "Ocean impact expected: evaluate bathymetry; plan coastal evacuation to higher ground.",
        "Keep ports clear; protect fuel/chemical tanks; reroute shipping lanes."
    ] if ocean else []

    # lead time фильтр для «космических» методов
    lt = max(0.0, float(lead_years))
    space_ok = []
    if lt >= 10:
        space_ok.append("Lead time sufficient for kinetic impactor mission(s) after reconnaissance flyby.")
    elif lt >= 5:
        space_ok.append("Borderline lead time: single kinetic impactor may help if launched promptly.")
    elif lt >= 1:
        space_ok.append("Too late for slow-push/gravity tractor; consider civil protection and last-minute measures only.")
    else:
        space_ok.append("No real time for orbital deflection; focus 100% on civil protection.")

    # собрать финальный список
    out = base.get(size_class, []).copy()
    out += airburst_tweaks if event_type == "airburst" else ground_tweaks
    out += ocean_block
    out += space_ok
    return out

# ============== NASA NEO API ==============
def get_neo_by_id(api_key: str, neo_id: str) -> dict:
    r = requests.get(f"{NASA_NEO_BASE}/neo/{neo_id}", params={"api_key": api_key}, timeout=20)
    r.raise_for_status()
    return r.json()

def browse_page(api_key: str, page: int = 0) -> dict:
    r = requests.get(f"{NASA_NEO_BASE}/neo/browse", params={"api_key": api_key, "page": page}, timeout=20)
    r.raise_for_status()
    return r.json()

def search_neo_by_name_exact(api_key: str, name: str, max_pages: int = 5) -> dict:
    target = name.strip().lower()
    for p in range(max_pages):
        data = browse_page(api_key, p)
        for neo in data.get("near_earth_objects", []):
            if neo.get("name", "").strip().lower() == target:
                return neo
    raise ValueError(f"Exact name not found in first {max_pages} pages")

def extract_params(neo_json: dict):
    meters = neo_json.get("estimated_diameter", {}).get("meters", {})
    d_min = meters.get("estimated_diameter_min"); d_max = meters.get("estimated_diameter_max")
    diameter = (d_min + d_max)/2 if d_min and d_max else None
    approaches = []
    for item in neo_json.get("close_approach_data", []):
        date = item.get("close_approach_date_full") or item.get("close_approach_date") or "N/A"
        v = None
        rel = item.get("relative_velocity", {})
        try:
            if rel.get("kilometers_per_second"):
                v = float(rel["kilometers_per_second"])
        except: v = None
        approaches.append((date, v))
    v_default = approaches[0][1] if approaches else None
    return diameter, v_default, approaches

# ============== Dark theme ==============
DARK_QSS = """
* { font-family: 'Segoe UI','Inter','Arial'; font-size: 13px; }
QWidget { background-color: #111317; color: #E6E6E6; }
QGroupBox { border: 1px solid #2A2F3A; border-radius: 10px; margin-top: 12px; padding: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #A9B1BD; }

QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
  background: #181C23; border: 1px solid #2A2F3A; border-radius: 8px; padding: 8px;
  selection-background-color: #2F80ED; color: #E6E6E6;
}
QPlainTextEdit { background: #0f1217; }
QTextEdit { background: #0f1217; }

QTabWidget::pane { border: 1px solid #2A2F3A; border-radius: 8px; top: -1px; background: #101318; }
QTabBar::tab { background: #181C23; color: #E6E6E6; padding: 8px 12px; border: 1px solid #2A2F3A;
               border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #141821; }
QTabBar::tab:hover { background: #1b202a; }

QPushButton { background: #2F80ED; border: none; color: #FFFFFF; padding: 10px 14px; border-radius: 10px; }
QPushButton:hover { background: #3B82F6; }
QPushButton#secondary { background: #2A2F3A; color: #E6E6E6; }
QPushButton#secondary:hover { background: #343A46; }

QLabel[hint="true"] { color: #9AA3AF; }
QStatusBar { background: #0D0F13; color: #A9B1BD; }
"""

# ============== “Map-like” view (no tiles) ==============
class RingsView(QtWidgets.QGraphicsView):
    """
    Интерактивная «карта» без тайлов:
      • колесо мыши — зум
      • ЛКМ — панорамирование
      • рисует сетку широта/долгота, подписи, линейку масштаба
      • кольца поражения остаются геометрически корректными (учёт широты по долготе)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QtGui.QColor("#0f1217"))
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)

      
        self.effects: dict | None = None
        self.lat: float = 0.0
        self.lon: float = 0.0

      
        self.zoom: float = 1.0        
        self.pan_dx: float = 0.0      
        self.pan_dy: float = 0.0      
        self._dragging = False
        self._last_pos = QtCore.QPointF()

        self._base_px_per_deg: float = 100.0

    def set_data(self, lat: float, lon: float, effects: dict):
        self.lat = float(lat)
        self.lon = float(lon)
        self.effects = effects or {}
        self.zoom = 1.0
        self.pan_dx = 0.0
        self.pan_dy = 0.0
        self.redraw()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.redraw()

    def wheelEvent(self, e: QtGui.QWheelEvent):
        if e.angleDelta().y() == 0:
            return
        factor = 1.2 if e.angleDelta().y() > 0 else 1/1.2
        self.zoom = min(20.0, max(0.2, self.zoom * factor))
        self.redraw()

    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_pos = e.position()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if self._dragging:
            delta = e.position() - self._last_pos
            self.pan_dx += float(delta.x())
            self.pan_dy += float(delta.y())
            self._last_pos = e.position()
            self.redraw()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QtGui.QMouseEvent):
        self.zoom = 1.0
        self.pan_dx = 0.0
        self.pan_dy = 0.0
        self.redraw()
        super().mouseDoubleClickEvent(e)

    # ---------- geometry ----------
    @staticmethod
    def km_to_deg_lat(km: float) -> float:
        return km / 110.574

    @staticmethod
    def km_to_deg_lon(km: float, lat_deg: float) -> float:
        c = max(0.1, math.cos(math.radians(lat_deg)))
        return km / (111.320 * c)

    @staticmethod
    def _nice_step(x: float) -> float:
        if x <= 0: return 1.0
        exp = math.floor(math.log10(x))
        frac = x / (10 ** exp)
        if frac < 1.5: nice = 1.0
        elif frac < 3.5: nice = 2.0
        elif frac < 7.5: nice = 5.0
        else: nice = 10.0
        return nice * (10 ** exp)

    # ----------painting
    def redraw(self):
        self.scene.clear()
        W = self.viewport().width()
        H = self.viewport().height()
        if W <= 0 or H <= 0:
            return

        # центр с учётом панорамирования
        cx, cy = W / 2 + self.pan_dx, H / 2 + self.pan_dy

        # максимальный радиус (км), чтобы подобрать масштаб
        Rmax_km = 1.0
        if self.effects:
            keys = [
                "light_blast_km",
                "moderate_blast_km",
                "severe_blast_km",
                "light_thermal_km",
                "severe_thermal_km",
            ]
            vals = [self.effects.get(k, 0.0) for k in keys]
            Rmax_km = max([v for v in vals if v], default=1.0)

        SAFE_MARGIN = 1.10  # 10% запас за самый большой радиус
        px_per_km = (min(W, H) / 2) / (max(Rmax_km, 1e-9) * SAFE_MARGIN)
        px_per_km *= self.zoom
        km_per_px = 1.0 / px_per_km


        # ===== Километровая сетка =====
        target_px = 120.0                       # целевые ~120 px между линиями
        step_km = self._nice_step(target_px * km_per_px)

        grid_pen = QtGui.QPen(QtGui.QColor("#222833"))
        grid_pen.setWidth(1)
        grid_pen.setCosmetic(True)

        label_color = QtGui.QColor("#9AA3AF")

        half_w_km = (W / 2) * km_per_px
        half_h_km = (H / 2) * km_per_px

        # вертикальные линии X (восток–запад)
        x0 = -math.floor(half_w_km / step_km) * step_km
        while x0 <= half_w_km + 1e-9:
            x = cx + (x0 * px_per_km)
            self.scene.addLine(x, 0, x, H, grid_pen)
            if abs(x0) > 1e-6:
                txt = f"{x0:+.0f} km"
                titem = self.scene.addText(txt, QtGui.QFont("Segoe UI", 9))
                titem.setDefaultTextColor(label_color)
                titem.setPos(x + 6, 10)
            x0 += step_km

        # горизонтальные линии Y (север–юг)
        y0 = -math.floor(half_h_km / step_km) * step_km
        while y0 <= half_h_km + 1e-9:
            y = cy - (y0 * px_per_km)            # экранная Y направлена вниз
            self.scene.addLine(0, y, W, y, grid_pen)
            if abs(y0) > 1e-6:
                txt = f"{y0:+.0f} km"
                titem = self.scene.addText(txt, QtGui.QFont("Segoe UI", 9))
                titem.setDefaultTextColor(label_color)
                titem.setPos(8, y - 14)
            y0 += step_km

        # линейка масштаба (в километрах), ~150 px
        scalebar_target_px = 150.0
        km_len = self._nice_step(scalebar_target_px * km_per_px)
        px_len = km_len * px_per_km
        sb_y = H - 24
        sb_x0 = 20
        sb_pen = QtGui.QPen(QtGui.QColor("#A9B1BD"))
        sb_pen.setWidth(2)
        sb_pen.setCosmetic(True)
        self.scene.addLine(sb_x0, sb_y, sb_x0 + px_len, sb_y, sb_pen)
        self.scene.addLine(sb_x0, sb_y - 5, sb_x0, sb_y + 5, sb_pen)
        self.scene.addLine(sb_x0 + px_len, sb_y - 5, sb_x0 + px_len, sb_y + 5, sb_pen)
        label = self.scene.addText(f"{km_len:.0f} km", QtGui.QFont("Segoe UI", 10))
        label.setDefaultTextColor(label_color)
        label.setPos(sb_x0 + px_len + 8, sb_y - 14)

        # ===== Кольца поражения (радиусы в км) =====
        def ring(radius_km: float, color_hex: str, alpha_fill: int, label: str | None = None):
            if not radius_km or radius_km <= 0:
                return
            r = radius_km * px_per_km
            pen = QtGui.QPen(QtGui.QColor(color_hex))
            pen.setWidth(2)
            pen.setCosmetic(True)
            col = QtGui.QColor(color_hex)
            col.setAlpha(alpha_fill)
            self.scene.addEllipse(cx - r, cy - r, 2 * r, 2 * r, pen, QtGui.QBrush(col))
            # подпись радиуса справа от окружности
            if label:
                txt = f"{label}: {radius_km:.1f} km"
                t = self.scene.addText(txt, QtGui.QFont("Segoe UI", 9))
                t.setDefaultTextColor(QtGui.QColor("#A9B1BD"))
                t.setPos(cx + r + 8, cy - 10)


        if self.effects:
            ring(self.effects.get("light_thermal_km"),  "#faad14", 32, "Light thermal")
            ring(self.effects.get("severe_thermal_km"), "#d46b08", 40, "Severe thermal")
            ring(self.effects.get("light_blast_km"),    "#fadb14", 28, "Light blast")
            ring(self.effects.get("moderate_blast_km"), "#fa8c16", 28, "Moderate blast")
            ring(self.effects.get("severe_blast_km"),   "#ff4d4f", 48, "Severe blast")


        # центр
        self.scene.addEllipse(cx - 5, cy - 5, 10, 10,
                            QtGui.QPen(QtCore.Qt.GlobalColor.transparent),
                            QtGui.QBrush(QtGui.QColor("#3291ff")))

        # легенда
        legend = [
            ("Severe blast",   "#ff4d4f"),
            ("Moderate blast", "#fa8c16"),
            ("Light blast",    "#fadb14"),
            ("Severe thermal", "#d46b08"),
            ("Light thermal",  "#faad14"),
        ]
        y = 10
        for text, color in legend:
            self.scene.addRect(10, y, 14, 8,
                            QtGui.QPen(QtGui.QColor(color)),
                            QtGui.QBrush(QtGui.QColor(color)))
            t = self.scene.addText(text, QtGui.QFont("Segoe UI", 9))
            t.setDefaultTextColor(QtGui.QColor("#9AA3AF"))
            t.setPos(30, y - 5)
            y += 18



# ============== Main Window ==============
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meteor Impact — PyQt6")
        self.resize(1000, 720)
        self.statusBar().showMessage("Ready")

        # state
        self.neo_loaded = False
        self.loaded_diameter = None
        self.approaches = []

        # --- Scrollable page (весь интерфейс прокручиваем целиком) ---
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        page = QtWidgets.QWidget()             # страница внутри скролла
        scroll.setWidget(page)

        root = QtWidgets.QVBoxLayout(page)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # --- Actions (buttons) ---
        g_act = QtWidgets.QGroupBox("Actions")
        act = QtWidgets.QHBoxLayout(g_act)

        self.resetBtn = QtWidgets.QPushButton("Reset")
        self.resetBtn.setObjectName("secondary")
        self.resetBtn.clicked.connect(self.on_reset)

        self.calcBtn  = QtWidgets.QPushButton("Calculate")
        self.calcBtn.clicked.connect(self.on_calc)   # <<< запускает расчёт и отрисовку карты

        act.addStretch(1)
        act.addWidget(self.resetBtn)
        act.addWidget(self.calcBtn)

        root.addWidget(g_act)


        # Header
        header = QtWidgets.QWidget()
        hv = QtWidgets.QVBoxLayout(header); hv.setContentsMargins(0,0,6,6)
        title = QtWidgets.QLabel("Meteor Impact — NEO Calculator")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        root.addWidget(header)

        # API & Search
        g_api = QtWidgets.QGroupBox("API  Search"); api = QtWidgets.QGridLayout(g_api)
        self.keyEdit = QtWidgets.QLineEdit(); self.keyEdit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.keyEdit.setPlaceholderText("NASA API Key (DEMO_KEY for tests)")
        self.modeCombo = QtWidgets.QComboBox(); self.modeCombo.addItems(["By ID","By exact name"])
        self.queryEdit = QtWidgets.QLineEdit(); self.queryEdit.setPlaceholderText("Enter NEO ID (e.g., 3542519) or exact name (e.g., Apophis)")
        self.pagesSpin = QtWidgets.QSpinBox(); self.pagesSpin.setRange(1,20); self.pagesSpin.setValue(5)
        self.fetchBtn = QtWidgets.QPushButton("Fetch from NASA"); self.fetchBtn.clicked.connect(self.on_fetch)
        self.useNASA = QtWidgets.QCheckBox("Use NASA data for calculations"); self.useNASA.stateChanged.connect(self.on_useNASA_changed)
        api.addWidget(QtWidgets.QLabel("API Key"),0,0); api.addWidget(self.keyEdit,0,1,1,3)
        api.addWidget(QtWidgets.QLabel("Mode"),1,0); api.addWidget(self.modeCombo,1,1)
        api.addWidget(self.queryEdit,1,2); api.addWidget(QtWidgets.QLabel("Pages"),1,3); api.addWidget(self.pagesSpin,1,4)
        api.addWidget(self.fetchBtn,2,4); api.addWidget(self.useNASA,2,0,1,3)
        root.addWidget(g_api)

        # Object
        g_obj = QtWidgets.QGroupBox("Object"); obj = QtWidgets.QFormLayout(g_obj)
        self.nameLabel = QtWidgets.QLabel("Name: —"); self.nameLabel.setProperty("hint", True)
        self.idLabel   = QtWidgets.QLabel("ID: —");   self.idLabel.setProperty("hint", True)
        self.approachCombo = QtWidgets.QComboBox(); self.approachCombo.currentIndexChanged.connect(self.on_approach_changed)
        obj.addRow(self.nameLabel); obj.addRow(self.idLabel); obj.addRow("Close approach:", self.approachCombo)
        root.addWidget(g_obj)

        # Parameters
        g_par = QtWidgets.QGroupBox("Parameters")
        par = QtWidgets.QFormLayout(g_par)
        self.diamSpin = QtWidgets.QDoubleSpinBox()
        self.diamSpin.setRange(0.001, 1e7)
        self.diamSpin.setDecimals(3)
        self.diamSpin.setValue(50.0)
        self.diamSpin.setSuffix(" m")

        self.velSpin  = QtWidgets.QDoubleSpinBox()
        self.velSpin.setRange(0.001, 200.0)
        self.velSpin.setDecimals(3)
        self.velSpin.setValue(20.0)
        self.velSpin.setSuffix(" km/s")

        self.rhoSpin  = QtWidgets.QDoubleSpinBox()
        self.rhoSpin.setRange(100.0, 20000.0)
        self.rhoSpin.setDecimals(1)
        self.rhoSpin.setValue(3000.0)
        self.rhoSpin.setSuffix(" kg/m³")

        self.angleSpin = QtWidgets.QDoubleSpinBox()
        self.angleSpin.setRange(1.0, 90.0)
        self.angleSpin.setDecimals(1)
        self.angleSpin.setValue(45.0)
        self.angleSpin.setSuffix(" °")

        self.latSpin  = QtWidgets.QDoubleSpinBox()
        self.latSpin.setRange(-90.0, 90.0)
        self.latSpin.setDecimals(6)
        self.latSpin.setValue(50.450001)
        self.latSpin.setSuffix(" °")

        self.lonSpin  = QtWidgets.QDoubleSpinBox()
        self.lonSpin.setRange(-180.0, 180.0)
        self.lonSpin.setDecimals(6)
        self.lonSpin.setValue(30.523333)
        self.lonSpin.setSuffix(" °")

      
        self.leadSpin = QtWidgets.QDoubleSpinBox()
        self.leadSpin.setRange(0.0, 100.0)
        self.leadSpin.setDecimals(1)
        self.leadSpin.setValue(5.0)
        self.leadSpin.setSuffix(" years")

        self.oceanCheck = QtWidgets.QCheckBox("Ocean impact")

      
        par.addRow("Diameter:", self.diamSpin)
        par.addRow("Velocity:", self.velSpin)
        par.addRow("Density:", self.rhoSpin)
        par.addRow("Entry angle:", self.angleSpin)
        par.addRow("Latitude:", self.latSpin)
        par.addRow("Longitude:", self.lonSpin)
        par.addRow("Lead time:", self.leadSpin)
        par.addRow("", self.oceanCheck)

        root.addWidget(g_par)

        tabs = QtWidgets.QTabWidget()

# Report tab
        report_tab = QtWidgets.QWidget()
        report_layout = QtWidgets.QVBoxLayout(report_tab)
        self.outText = QtWidgets.QPlainTextEdit()
        self.outText.setReadOnly(True)
        self.outText.setFont(QtGui.QFont("Consolas", 11))
        self.outText.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                QtWidgets.QSizePolicy.Policy.Expanding)
        report_layout.addWidget(self.outText)
        tabs.addTab(report_tab, "Report")

        # Map tab
        self.ringsView = RingsView()
        self.ringsView.setMinimumHeight(360)
        self.ringsView.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                    QtWidgets.QSizePolicy.Policy.Expanding)
        tabs.addTab(self.ringsView, "Impact Map")

        root.addWidget(tabs, 1)

        # theme
        self.setStyleSheet(DARK_QSS)
        self.ringsView.set_data(0.0, 0.0, {})  # пустая тёмная сцена

    # helpers
    def set_manual_fields_readonly(self, ro: bool):
        self.diamSpin.setReadOnly(ro); self.velSpin.setReadOnly(ro)
        style = "background:#1D232E;" if ro else ""
        self.diamSpin.setStyleSheet(style); self.velSpin.setStyleSheet(style)

    def on_useNASA_changed(self, _=None):
        if self.useNASA.isChecked() and not self.neo_loaded:
            QtWidgets.QMessageBox.information(self, "No data", "Fetch NASA data first.")
            self.useNASA.setChecked(False); return
        self.set_manual_fields_readonly(self.useNASA.isChecked())

    def populate_approaches(self):
        self.approachCombo.blockSignals(True); self.approachCombo.clear()
        for date, v in self.approaches:
            lbl = f"{date} — {v:.3f} km/s" if isinstance(v,(int,float)) else f"{date} — n/a"
            self.approachCombo.addItem(lbl, v)
        self.approachCombo.blockSignals(False)

    def on_approach_changed(self, idx: int):
        if idx < 0: return
        v = self.approachCombo.currentData()
        if isinstance(v,(int,float)): self.velSpin.setValue(float(v))

    def on_fetch(self):
        api = (self.keyEdit.text() or "DEMO_KEY").strip()
        q = (self.queryEdit.text() or "").strip()
        if not q:
            QtWidgets.QMessageBox.warning(self, "Warning", "Enter ID or exact name."); return
        try:
            self.statusBar().showMessage("Fetching…")
            if self.modeCombo.currentText() == "By ID":
                neo = get_neo_by_id(api, q)
            else:
                neo = search_neo_by_name_exact(api, q, int(self.pagesSpin.value()))
            name = neo.get("name","—"); neo_id = neo.get("id","—")
            self.nameLabel.setText(f"Name: {name}"); self.idLabel.setText(f"ID: {neo_id}")
            d, v_default, approaches = extract_params(neo)
            self.neo_loaded = True; self.loaded_diameter = d; self.approaches = approaches or []
            if d is not None: self.diamSpin.setValue(float(d))
            if v_default is not None: self.velSpin.setValue(float(v_default))
            self.populate_approaches()
            self.statusBar().showMessage("NASA data loaded"); self.outText.clear()
        except requests.HTTPError as e:
            QtWidgets.QMessageBox.critical(self, "HTTP error", f"{e}\n{getattr(e.response,'text','')[:500]}")
            self.statusBar().showMessage("Error")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e)); self.statusBar().showMessage("Error")

    def on_calc(self):
        if self.useNASA.isChecked():
            if not self.neo_loaded:
                QtWidgets.QMessageBox.warning(self, "No NASA data", "Fetch from NASA first or turn off the toggle."); return
            if self.loaded_diameter is None:
                QtWidgets.QMessageBox.warning(self, "Missing diameter", "NASA did not provide diameter."); return
            v_sel = self.approachCombo.currentData()
            if not isinstance(v_sel,(int,float)):
                QtWidgets.QMessageBox.warning(self, "Missing velocity", "Selected approach has no velocity."); return
            d = float(self.loaded_diameter); v = float(v_sel); source = "NASA (object data)"
        else:
            d = float(self.diamSpin.value()); v = float(self.velSpin.value()); source = "Manual input"

        rho = float(self.rhoSpin.value()); angle = float(self.angleSpin.value())
        lat = float(self.latSpin.value()); lon = float(self.lonSpin.value())

        m = mass_from_diameter(d, rho)
        E = kinetic_energy_joules(m, v)
        mt = joules_to_megatons_tnt(E)
        effects = impact_effects(mt, angle)
        # mitigation advice
        size_cls = classify_size(d)
        event_type = guess_event_type(d, angle)
        adv = mitigation_brief(size_cls, event_type, self.leadSpin.value(), self.oceanCheck.isChecked())


        lines = []
        lines.append("=== Impact Report ===")
        lines.append(f"Parameter source: {source}")
        lines.append(f"Diameter: {d:,.3f} m")
        lines.append(f"Density: {rho:,.1f} kg/m³")
        lines.append(f"Velocity: {v:,.3f} km/s")
        lines.append(f"Entry angle: {angle:.1f} deg")
        lines.append(f"Mass: {m:,.0f} kg")
        lines.append(f"Energy: {E:,.3e} J")
        lines.append(f"Kinetic yield: {mt:.6f} Mt TNT")
        lines.append(f"Effective surface yield: {effects['effective_surface_yield_mt']:.6f} Mt TNT")
        lines.append("Estimated damage radii:")
        for k in ["severe_blast_km","moderate_blast_km","light_blast_km","severe_thermal_km","light_thermal_km"]:
            if k in effects:
                label = k.replace("_"," ").title().replace("Km","km")
                lines.append(f"  • {label}: {effects[k]:.3f} km")
        lines.append("\nMitigation (summary):")
        lines.append("  • Long-term: kinetic impactor (DART-proven), gravity tractor; years of lead time.")
        lines.append("  • Last-minute: evacuate severe/moderate blast zones; avoid windows; prep firebreaks; coastal: tsunami routes.")
        lines.append("  • Nuclear standoff: politically complex; only for late-detected large objects; fragmentation risk.")

        lines.append("\nMitigation (auto-brief):")
        lines.append(f"  • Size class: {size_cls}    Event: {event_type}    Lead time: {self.leadSpin.value():.1f} years    Ocean: {'yes' if self.oceanCheck.isChecked() else 'no'}")
        for tip in adv:
            lines.append(f"    - {tip}")


        self.outText.setPlainText("\n".join(lines))
        self.ringsView.set_data(lat, lon, effects)
        self.statusBar().showMessage("Calculated")

    def on_reset(self):
        self.neo_loaded = False; self.loaded_diameter = None; self.approaches = []
        self.useNASA.setChecked(False); self.set_manual_fields_readonly(False)
        self.nameLabel.setText("Name: —"); self.idLabel.setText("ID: —"); self.approachCombo.clear()
        self.diamSpin.setValue(50.0); self.velSpin.setValue(20.0); self.rhoSpin.setValue(3000.0)
        self.angleSpin.setValue(45.0); self.latSpin.setValue(50.450001); self.lonSpin.setValue(30.523333)
        self.outText.clear(); self.ringsView.set_data(0.0, 0.0, {}); self.statusBar().showMessage("Reset")

# ============== main() ==============
def main():
    app = QtWidgets.QApplication(sys.argv)
    attr = QtCore.Qt.ApplicationAttribute
    if hasattr(attr, "UseHighDpiPixmaps"):
        app.setAttribute(attr.UseHighDpiPixmaps)
    elif hasattr(attr, "AA_UseHighDpiPixmaps"):
        app.setAttribute(attr.AA_UseHighDpiPixmaps)

    app.setStyleSheet(DARK_QSS)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
