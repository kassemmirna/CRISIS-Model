# =============================================================================
# crisis_params.py  —  Single source of truth for all CRISIS model parameters.
# =============================================================================
# crisis_gui.py reads this at startup and builds its form dynamically.
# Adding a parameter here automatically adds it to the GUI on next launch.
# forward_analysis.py receives all parameters as a plain dict keyed by 'key'.
#
# NAMING CONVENTION:
#   Parameters whose key begins with 'ba_' belong to the Back-Analysis module
#   (back_analysis.py).  The 'ba_' prefix exists only inside the GUI so that
#   parameters with the same physical meaning (e.g. dem_file, Cell_size) can
#   coexist for both the forward-analysis and back-analysis tabs without
#   collision.  The GUI strips the prefix before passing values to
#   back_analysis.run_model(), which uses clean key names matching
#   config_back_analysis_windows.json.
#
# PARAM FIELDS:
#   key          : variable name used in forward_analysis.py (or ba_<name> for back-analysis)
#   label        : human-readable label shown in the GUI
#   type         : 'float' | 'int' | 'str' | 'choice' | 'file' | 'dir'
#   default      : default value
#   category     : tab name (must exist in PARAM_CATEGORIES)
#   description  : tooltip text shown on hover
#   choices      : list of (raw_value, display_label)  — for type='choice'
#   show_if      : {'param': 'other_key', 'value': raw_value}  — or a list of such dicts (OR logic)
#   required     : True if an empty value is an error (default False)
#   file_filter  : e.g. 'HDF5 files (*.h5)'  — only for type='file'
# =============================================================================

PARAM_CATEGORIES = [
    'Project Details',
    'Triggering Event',
    'Topography',             # DEM + Cell_size + xmin/ymin; Slope, Flow Direction,
                               # Flow Accumulation, and x/y coordinates are auto-derived
    'Scalar Inputs',
    'Hydrological Formulations',
    'Earthquake Inputs',      # Only shown when Triggering_Indicator == 2 (Rainfall +
                               # Earthquake) — model choice, PGA/PGV rasters, fault
                               # geometry, and seismic scalars all live here
    'Shear Strength',
    # ── Back-Analysis (BA) tabs — keys are prefixed with 'ba_' to avoid
    # collision with identically-named forward-analysis parameters ──────────────
    'BA Raster Inputs',       # Back-Analysis: topographic raster files
    'BA Scalar Inputs',       # Back-Analysis: grid dimensions and search parameters
    'BA Hydrology',           # Back-Analysis: pore pressure and water content files
    'BA Shear Strength',      # Back-Analysis: cohesion / friction angle search ranges
    'Mapped Landslide Inventory',
]

PARAMS = [

    # =========================================================================
    # Project Details
    # =========================================================================
    {
        'key': 'analysis_type',
        'label': 'Analysis Type',
        'type': 'choice',
        'default': '',
        'category': 'Project Details',
        'description': (
            'Forward Predictive Analysis: predict landslides induced by a rainfall / earthquake event.\n'
            'Back-Analysis: back-analyze landslides triggered by a rainfall event to estimate shear strength parameters.'
        ),
        'choices': [
            ('forward', 'Forward Predictive Analysis'),
            ('back',    'Back-Analysis'),
        ],
        'required': True,
    },
    {
        'key': 'project_title',
        'label': 'Project Title',
        'type': 'str',
        'default': '',
        'category': 'Project Details',
        'description': 'Name or title for this analysis project.',
    },
    {
        'key': 'analyst_name',
        'label': 'User Name',
        'type': 'str',
        'default': '',
        'category': 'Project Details',
        'description': 'Name of user running this analysis.',
    },
    {
        'key': 'project_date',
        'label': 'Date',
        'type': 'str',
        'default': '',
        'category': 'Project Details',
        'description': 'Date of analysis (e.g. 2025-05-03).',
    },
    {
        'key': 'site_location',
        'label': 'Site Location / Study Area',
        'type': 'str',
        'default': '',
        'category': 'Project Details',
        'description': 'Geographic location or name of the study area.',
    },
    {
        'key': 'output_dir',
        'label': 'Output Directory',
        'type': 'dir',
        'default': '',
        'category': 'Project Details',
        'description': (
            'Folder where all outputs will be saved.\n'
            'A sub-folder named "{Project Title}_Outputs" will be created automatically.'
        ),
        'required': True,
    },
    {
        'key': 'Coordinate_Reference_System',
        'label': 'Coordinate Reference System',
        'type': 'searchable_choice',
        'default': '',
        'choices': [
            # ------------------------------------------------------------------
            # Web / Global Projected
            # ------------------------------------------------------------------
            ('EPSG:3857',  'WGS 84 / Web Mercator (Pseudo-Mercator)'),
            ('ESRI:54009', 'World Mollweide (Esri)'),
            ('ESRI:54008', 'World Sinusoidal (Esri)'),
            ('ESRI:54034', 'World Cylindrical Equal Area (Esri)'),
            # ------------------------------------------------------------------
            # UTM WGS 84 — North (Zones 1N – 60N)
            # ------------------------------------------------------------------
            ('EPSG:32601', 'UTM Zone 1N  (180°W – 174°W)'),
            ('EPSG:32602', 'UTM Zone 2N  (174°W – 168°W)'),
            ('EPSG:32603', 'UTM Zone 3N  (168°W – 162°W)'),
            ('EPSG:32604', 'UTM Zone 4N  (162°W – 156°W)'),
            ('EPSG:32605', 'UTM Zone 5N  (156°W – 150°W)'),
            ('EPSG:32606', 'UTM Zone 6N  (150°W – 144°W)'),
            ('EPSG:32607', 'UTM Zone 7N  (144°W – 138°W)'),
            ('EPSG:32608', 'UTM Zone 8N  (138°W – 132°W)'),
            ('EPSG:32609', 'UTM Zone 9N  (132°W – 126°W)'),
            ('EPSG:32610', 'UTM Zone 10N (126°W – 120°W)'),
            ('EPSG:32611', 'UTM Zone 11N (120°W – 114°W)'),
            ('EPSG:32612', 'UTM Zone 12N (114°W – 108°W)'),
            ('EPSG:32613', 'UTM Zone 13N (108°W – 102°W)'),
            ('EPSG:32614', 'UTM Zone 14N (102°W –  96°W)'),
            ('EPSG:32615', 'UTM Zone 15N  (96°W –  90°W)'),
            ('EPSG:32616', 'UTM Zone 16N  (90°W –  84°W)'),
            ('EPSG:32617', 'UTM Zone 17N  (84°W –  78°W)'),
            ('EPSG:32618', 'UTM Zone 18N  (78°W –  72°W)'),
            ('EPSG:32619', 'UTM Zone 19N  (72°W –  66°W)'),
            ('EPSG:32620', 'UTM Zone 20N  (66°W –  60°W)'),
            ('EPSG:32621', 'UTM Zone 21N  (60°W –  54°W)'),
            ('EPSG:32622', 'UTM Zone 22N  (54°W –  48°W)'),
            ('EPSG:32623', 'UTM Zone 23N  (48°W –  42°W)'),
            ('EPSG:32624', 'UTM Zone 24N  (42°W –  36°W)'),
            ('EPSG:32625', 'UTM Zone 25N  (36°W –  30°W)'),
            ('EPSG:32626', 'UTM Zone 26N  (30°W –  24°W)'),
            ('EPSG:32627', 'UTM Zone 27N  (24°W –  18°W)'),
            ('EPSG:32628', 'UTM Zone 28N  (18°W –  12°W)'),
            ('EPSG:32629', 'UTM Zone 29N  (12°W –   6°W)'),
            ('EPSG:32630', 'UTM Zone 30N   (6°W –    0°)'),
            ('EPSG:32631', 'UTM Zone 31N    (0°  –   6°E)'),
            ('EPSG:32632', 'UTM Zone 32N   (6°E –  12°E)'),
            ('EPSG:32633', 'UTM Zone 33N  (12°E –  18°E)'),
            ('EPSG:32634', 'UTM Zone 34N  (18°E –  24°E)'),
            ('EPSG:32635', 'UTM Zone 35N  (24°E –  30°E)'),
            ('EPSG:32636', 'UTM Zone 36N  (30°E –  36°E)'),
            ('EPSG:32637', 'UTM Zone 37N  (36°E –  42°E)'),
            ('EPSG:32638', 'UTM Zone 38N  (42°E –  48°E)'),
            ('EPSG:32639', 'UTM Zone 39N  (48°E –  54°E)'),
            ('EPSG:32640', 'UTM Zone 40N  (54°E –  60°E)'),
            ('EPSG:32641', 'UTM Zone 41N  (60°E –  66°E)'),
            ('EPSG:32642', 'UTM Zone 42N  (66°E –  72°E)'),
            ('EPSG:32643', 'UTM Zone 43N  (72°E –  78°E)'),
            ('EPSG:32644', 'UTM Zone 44N  (78°E –  84°E)'),
            ('EPSG:32645', 'UTM Zone 45N  (84°E –  90°E)'),
            ('EPSG:32646', 'UTM Zone 46N  (90°E –  96°E)'),
            ('EPSG:32647', 'UTM Zone 47N  (96°E – 102°E)'),
            ('EPSG:32648', 'UTM Zone 48N (102°E – 108°E)'),
            ('EPSG:32649', 'UTM Zone 49N (108°E – 114°E)'),
            ('EPSG:32650', 'UTM Zone 50N (114°E – 120°E)'),
            ('EPSG:32651', 'UTM Zone 51N (120°E – 126°E)'),
            ('EPSG:32652', 'UTM Zone 52N (126°E – 132°E)'),
            ('EPSG:32653', 'UTM Zone 53N (132°E – 138°E)'),
            ('EPSG:32654', 'UTM Zone 54N (138°E – 144°E)'),
            ('EPSG:32655', 'UTM Zone 55N (144°E – 150°E)'),
            ('EPSG:32656', 'UTM Zone 56N (150°E – 156°E)'),
            ('EPSG:32657', 'UTM Zone 57N (156°E – 162°E)'),
            ('EPSG:32658', 'UTM Zone 58N (162°E – 168°E)'),
            ('EPSG:32659', 'UTM Zone 59N (168°E – 174°E)'),
            ('EPSG:32660', 'UTM Zone 60N (174°E – 180°E)'),
            # ------------------------------------------------------------------
            # UTM WGS 84 — South (Zones 1S – 60S)
            # ------------------------------------------------------------------
            ('EPSG:32701', 'UTM Zone 1S'),
            ('EPSG:32702', 'UTM Zone 2S'),
            ('EPSG:32703', 'UTM Zone 3S'),
            ('EPSG:32704', 'UTM Zone 4S'),
            ('EPSG:32705', 'UTM Zone 5S'),
            ('EPSG:32706', 'UTM Zone 6S'),
            ('EPSG:32707', 'UTM Zone 7S'),
            ('EPSG:32708', 'UTM Zone 8S'),
            ('EPSG:32709', 'UTM Zone 9S'),
            ('EPSG:32710', 'UTM Zone 10S'),
            ('EPSG:32711', 'UTM Zone 11S'),
            ('EPSG:32712', 'UTM Zone 12S'),
            ('EPSG:32713', 'UTM Zone 13S'),
            ('EPSG:32714', 'UTM Zone 14S'),
            ('EPSG:32715', 'UTM Zone 15S'),
            ('EPSG:32716', 'UTM Zone 16S'),
            ('EPSG:32717', 'UTM Zone 17S'),
            ('EPSG:32718', 'UTM Zone 18S'),
            ('EPSG:32719', 'UTM Zone 19S'),
            ('EPSG:32720', 'UTM Zone 20S'),
            ('EPSG:32721', 'UTM Zone 21S'),
            ('EPSG:32722', 'UTM Zone 22S'),
            ('EPSG:32723', 'UTM Zone 23S'),
            ('EPSG:32724', 'UTM Zone 24S'),
            ('EPSG:32725', 'UTM Zone 25S'),
            ('EPSG:32726', 'UTM Zone 26S'),
            ('EPSG:32727', 'UTM Zone 27S'),
            ('EPSG:32728', 'UTM Zone 28S'),
            ('EPSG:32729', 'UTM Zone 29S'),
            ('EPSG:32730', 'UTM Zone 30S'),
            ('EPSG:32731', 'UTM Zone 31S'),
            ('EPSG:32732', 'UTM Zone 32S'),
            ('EPSG:32733', 'UTM Zone 33S'),
            ('EPSG:32734', 'UTM Zone 34S'),
            ('EPSG:32735', 'UTM Zone 35S'),
            ('EPSG:32736', 'UTM Zone 36S'),
            ('EPSG:32737', 'UTM Zone 37S'),
            ('EPSG:32738', 'UTM Zone 38S'),
            ('EPSG:32739', 'UTM Zone 39S'),
            ('EPSG:32740', 'UTM Zone 40S'),
            ('EPSG:32741', 'UTM Zone 41S'),
            ('EPSG:32742', 'UTM Zone 42S'),
            ('EPSG:32743', 'UTM Zone 43S'),
            ('EPSG:32744', 'UTM Zone 44S'),
            ('EPSG:32745', 'UTM Zone 45S'),
            ('EPSG:32746', 'UTM Zone 46S'),
            ('EPSG:32747', 'UTM Zone 47S'),
            ('EPSG:32748', 'UTM Zone 48S'),
            ('EPSG:32749', 'UTM Zone 49S'),
            ('EPSG:32750', 'UTM Zone 50S'),
            ('EPSG:32751', 'UTM Zone 51S'),
            ('EPSG:32752', 'UTM Zone 52S'),
            ('EPSG:32753', 'UTM Zone 53S'),
            ('EPSG:32754', 'UTM Zone 54S'),
            ('EPSG:32755', 'UTM Zone 55S'),
            ('EPSG:32756', 'UTM Zone 56S'),
            ('EPSG:32757', 'UTM Zone 57S'),
            ('EPSG:32758', 'UTM Zone 58S'),
            ('EPSG:32759', 'UTM Zone 59S'),
            ('EPSG:32760', 'UTM Zone 60S'),
            # ------------------------------------------------------------------
            # UTM NAD 83 — North (Zones 1N – 23N, North America)
            # ------------------------------------------------------------------
            ('EPSG:26901', 'NAD83 / UTM Zone 1N'),
            ('EPSG:26902', 'NAD83 / UTM Zone 2N'),
            ('EPSG:26903', 'NAD83 / UTM Zone 3N'),
            ('EPSG:26904', 'NAD83 / UTM Zone 4N'),
            ('EPSG:26905', 'NAD83 / UTM Zone 5N'),
            ('EPSG:26906', 'NAD83 / UTM Zone 6N'),
            ('EPSG:26907', 'NAD83 / UTM Zone 7N'),
            ('EPSG:26908', 'NAD83 / UTM Zone 8N'),
            ('EPSG:26909', 'NAD83 / UTM Zone 9N'),
            ('EPSG:26910', 'NAD83 / UTM Zone 10N'),
            ('EPSG:26911', 'NAD83 / UTM Zone 11N'),
            ('EPSG:26912', 'NAD83 / UTM Zone 12N'),
            ('EPSG:26913', 'NAD83 / UTM Zone 13N'),
            ('EPSG:26914', 'NAD83 / UTM Zone 14N'),
            ('EPSG:26915', 'NAD83 / UTM Zone 15N'),
            ('EPSG:26916', 'NAD83 / UTM Zone 16N'),
            ('EPSG:26917', 'NAD83 / UTM Zone 17N'),
            ('EPSG:26918', 'NAD83 / UTM Zone 18N'),
            ('EPSG:26919', 'NAD83 / UTM Zone 19N'),
            ('EPSG:26920', 'NAD83 / UTM Zone 20N'),
            ('EPSG:26921', 'NAD83 / UTM Zone 21N'),
            ('EPSG:26922', 'NAD83 / UTM Zone 22N'),
            ('EPSG:26923', 'NAD83 / UTM Zone 23N'),
            # ------------------------------------------------------------------
            # US State Plane — NAD 83 (meters)
            # ------------------------------------------------------------------
            ('EPSG:26929', 'NAD83 / Alabama East'),
            ('EPSG:26930', 'NAD83 / Alabama West'),
            ('EPSG:26931', 'NAD83 / Alaska Zone 1'),
            ('EPSG:26932', 'NAD83 / Alaska Zone 2'),
            ('EPSG:26933', 'NAD83 / Alaska Zone 3'),
            ('EPSG:26934', 'NAD83 / Alaska Zone 4'),
            ('EPSG:26935', 'NAD83 / Alaska Zone 5'),
            ('EPSG:26936', 'NAD83 / Alaska Zone 6'),
            ('EPSG:26937', 'NAD83 / Alaska Zone 7'),
            ('EPSG:26938', 'NAD83 / Alaska Zone 8'),
            ('EPSG:26939', 'NAD83 / Alaska Zone 9'),
            ('EPSG:26940', 'NAD83 / Alaska Zone 10'),
            ('EPSG:26948', 'NAD83 / Arizona East'),
            ('EPSG:26949', 'NAD83 / Arizona Central'),
            ('EPSG:26950', 'NAD83 / Arizona West'),
            ('EPSG:26951', 'NAD83 / Arkansas North'),
            ('EPSG:26952', 'NAD83 / Arkansas South'),
            ('EPSG:26941', 'NAD83 / California Zone 1'),
            ('EPSG:26942', 'NAD83 / California Zone 2'),
            ('EPSG:26943', 'NAD83 / California Zone 3'),
            ('EPSG:26944', 'NAD83 / California Zone 4'),
            ('EPSG:26945', 'NAD83 / California Zone 5'),
            ('EPSG:26946', 'NAD83 / California Zone 6'),
            ('EPSG:6566',  'NAD83 / California Teale Albers'),
            ('EPSG:26953', 'NAD83 / Colorado North'),
            ('EPSG:26954', 'NAD83 / Colorado Central'),
            ('EPSG:26955', 'NAD83 / Colorado South'),
            ('EPSG:26956', 'NAD83 / Connecticut'),
            ('EPSG:26957', 'NAD83 / Delaware'),
            ('EPSG:26958', 'NAD83 / Florida East'),
            ('EPSG:26959', 'NAD83 / Florida West'),
            ('EPSG:26960', 'NAD83 / Florida North'),
            ('EPSG:26966', 'NAD83 / Georgia East'),
            ('EPSG:26967', 'NAD83 / Georgia West'),
            ('EPSG:26961', 'NAD83 / Hawaii Zone 1'),
            ('EPSG:26962', 'NAD83 / Hawaii Zone 2'),
            ('EPSG:26963', 'NAD83 / Hawaii Zone 3'),
            ('EPSG:26964', 'NAD83 / Hawaii Zone 4'),
            ('EPSG:26965', 'NAD83 / Hawaii Zone 5'),
            ('EPSG:26968', 'NAD83 / Idaho East'),
            ('EPSG:26969', 'NAD83 / Idaho Central'),
            ('EPSG:26970', 'NAD83 / Idaho West'),
            ('EPSG:26971', 'NAD83 / Illinois East'),
            ('EPSG:26972', 'NAD83 / Illinois West'),
            ('EPSG:26973', 'NAD83 / Indiana East'),
            ('EPSG:26974', 'NAD83 / Indiana West'),
            ('EPSG:26975', 'NAD83 / Iowa North'),
            ('EPSG:26976', 'NAD83 / Iowa South'),
            ('EPSG:26977', 'NAD83 / Kansas North'),
            ('EPSG:26978', 'NAD83 / Kansas South'),
            ('EPSG:26979', 'NAD83 / Kentucky North'),
            ('EPSG:26980', 'NAD83 / Kentucky South'),
            ('EPSG:26981', 'NAD83 / Louisiana North'),
            ('EPSG:26982', 'NAD83 / Louisiana South'),
            ('EPSG:26983', 'NAD83 / Maine East'),
            ('EPSG:26984', 'NAD83 / Maine West'),
            ('EPSG:26985', 'NAD83 / Maryland'),
            ('EPSG:26986', 'NAD83 / Massachusetts Mainland'),
            ('EPSG:26987', 'NAD83 / Massachusetts Island'),
            ('EPSG:26988', 'NAD83 / Michigan North'),
            ('EPSG:26989', 'NAD83 / Michigan Central'),
            ('EPSG:26990', 'NAD83 / Michigan South'),
            ('EPSG:26991', 'NAD83 / Minnesota North'),
            ('EPSG:26992', 'NAD83 / Minnesota Central'),
            ('EPSG:26993', 'NAD83 / Minnesota South'),
            ('EPSG:26994', 'NAD83 / Mississippi East'),
            ('EPSG:26995', 'NAD83 / Mississippi West'),
            ('EPSG:26996', 'NAD83 / Missouri East'),
            ('EPSG:26997', 'NAD83 / Missouri Central'),
            ('EPSG:26998', 'NAD83 / Missouri West'),
            ('EPSG:32100', 'NAD83 / Montana'),
            ('EPSG:32104', 'NAD83 / Nebraska'),
            ('EPSG:32107', 'NAD83 / Nevada East'),
            ('EPSG:32108', 'NAD83 / Nevada Central'),
            ('EPSG:32109', 'NAD83 / Nevada West'),
            ('EPSG:32110', 'NAD83 / New Hampshire'),
            ('EPSG:32111', 'NAD83 / New Jersey'),
            ('EPSG:32112', 'NAD83 / New Mexico East'),
            ('EPSG:32113', 'NAD83 / New Mexico Central'),
            ('EPSG:32114', 'NAD83 / New Mexico West'),
            ('EPSG:32115', 'NAD83 / New York East'),
            ('EPSG:32116', 'NAD83 / New York Central'),
            ('EPSG:32117', 'NAD83 / New York West'),
            ('EPSG:32118', 'NAD83 / New York Long Island'),
            ('EPSG:32119', 'NAD83 / North Carolina'),
            ('EPSG:32120', 'NAD83 / North Dakota North'),
            ('EPSG:32121', 'NAD83 / North Dakota South'),
            ('EPSG:32122', 'NAD83 / Ohio North'),
            ('EPSG:32123', 'NAD83 / Ohio South'),
            ('EPSG:32124', 'NAD83 / Oklahoma North'),
            ('EPSG:32125', 'NAD83 / Oklahoma South'),
            ('EPSG:32126', 'NAD83 / Oregon North'),
            ('EPSG:32127', 'NAD83 / Oregon South'),
            ('EPSG:32128', 'NAD83 / Pennsylvania North'),
            ('EPSG:32129', 'NAD83 / Pennsylvania South'),
            ('EPSG:32130', 'NAD83 / Rhode Island'),
            ('EPSG:32133', 'NAD83 / South Carolina'),
            ('EPSG:32134', 'NAD83 / South Dakota North'),
            ('EPSG:32135', 'NAD83 / South Dakota South'),
            ('EPSG:32136', 'NAD83 / Tennessee'),
            ('EPSG:32137', 'NAD83 / Texas North'),
            ('EPSG:32138', 'NAD83 / Texas North Central'),
            ('EPSG:32139', 'NAD83 / Texas Central'),
            ('EPSG:32140', 'NAD83 / Texas South Central'),
            ('EPSG:32141', 'NAD83 / Texas South'),
            ('EPSG:32142', 'NAD83 / Utah North'),
            ('EPSG:32143', 'NAD83 / Utah Central'),
            ('EPSG:32144', 'NAD83 / Utah South'),
            ('EPSG:32145', 'NAD83 / Vermont'),
            ('EPSG:32146', 'NAD83 / Virginia North'),
            ('EPSG:32147', 'NAD83 / Virginia South'),
            ('EPSG:32148', 'NAD83 / Washington North'),
            ('EPSG:32149', 'NAD83 / Washington South'),
            ('EPSG:32150', 'NAD83 / West Virginia North'),
            ('EPSG:32151', 'NAD83 / West Virginia South'),
            ('EPSG:32152', 'NAD83 / Wisconsin North'),
            ('EPSG:32153', 'NAD83 / Wisconsin Central'),
            ('EPSG:32154', 'NAD83 / Wisconsin South'),
            ('EPSG:32155', 'NAD83 / Wyoming East'),
            ('EPSG:32156', 'NAD83 / Wyoming East Central'),
            ('EPSG:32157', 'NAD83 / Wyoming West Central'),
            ('EPSG:32158', 'NAD83 / Wyoming West'),
            ('EPSG:32161', 'NAD83 / Puerto Rico & Virgin Islands'),
            # ------------------------------------------------------------------
            # European / ETRS89 National Grids
            # ------------------------------------------------------------------
            ('EPSG:25829', 'ETRS89 / UTM zone 29N'),
            ('EPSG:25830', 'ETRS89 / UTM zone 30N'),
            ('EPSG:25831', 'ETRS89 / UTM zone 31N'),
            ('EPSG:25832', 'ETRS89 / UTM zone 32N'),
            ('EPSG:25833', 'ETRS89 / UTM zone 33N'),
            ('EPSG:25834', 'ETRS89 / UTM zone 34N'),
            ('EPSG:25835', 'ETRS89 / UTM zone 35N'),
            ('EPSG:25836', 'ETRS89 / UTM zone 36N'),
            ('EPSG:25837', 'ETRS89 / UTM zone 37N'),
            ('EPSG:27700', 'British National Grid (OSGB 1936)'),
            ('EPSG:2154',  'RGF93 / Lambert-93 (France)'),
            ('EPSG:3034',  'ETRS89 / LCC Europe'),
            ('EPSG:3035',  'ETRS89 / LAEA Europe'),
            ('EPSG:3044',  'ETRS89 / TM32 (Germany)'),
            ('EPSG:3045',  'ETRS89 / TM33 (Germany)'),
            ('EPSG:4647',  'ETRS89 / UTM zone 32N (N-E)'),
            ('EPSG:5650',  'ETRS89 / UTM zone 33N (N-E)'),
            ('EPSG:2180',  'ETRS89 / Poland CS92'),
            ('EPSG:3301',  'Estonian Coordinate System of 1997'),
            ('EPSG:3346',  'LKS94 / Lithuania TM'),
            ('EPSG:3059',  'LKS92 / Latvia TM'),
            # ------------------------------------------------------------------
            # Australia & New Zealand
            # ------------------------------------------------------------------
            ('EPSG:28348', 'GDA94 / MGA zone 48'),
            ('EPSG:28349', 'GDA94 / MGA zone 49'),
            ('EPSG:28350', 'GDA94 / MGA zone 50'),
            ('EPSG:28351', 'GDA94 / MGA zone 51'),
            ('EPSG:28352', 'GDA94 / MGA zone 52'),
            ('EPSG:28353', 'GDA94 / MGA zone 53'),
            ('EPSG:28354', 'GDA94 / MGA zone 54'),
            ('EPSG:28355', 'GDA94 / MGA zone 55'),
            ('EPSG:28356', 'GDA94 / MGA zone 56'),
            ('EPSG:7850',  'GDA2020 / MGA zone 50'),
            ('EPSG:7851',  'GDA2020 / MGA zone 51'),
            ('EPSG:7852',  'GDA2020 / MGA zone 52'),
            ('EPSG:7853',  'GDA2020 / MGA zone 53'),
            ('EPSG:7854',  'GDA2020 / MGA zone 54'),
            ('EPSG:7855',  'GDA2020 / MGA zone 55'),
            ('EPSG:7856',  'GDA2020 / MGA zone 56'),
            ('EPSG:2193',  'NZGD2000 / New Zealand Transverse Mercator'),
            # ------------------------------------------------------------------
            # Asia
            # ------------------------------------------------------------------
            ('EPSG:4547',  'CGCS2000 / Gauss-Kruger zone 39'),
            ('EPSG:4548',  'CGCS2000 / Gauss-Kruger zone 40'),
            ('EPSG:3097',  'JGD2000 / Japan Plane Rectangular CS I'),
            ('EPSG:3098',  'JGD2000 / Japan Plane Rectangular CS II'),
            ('EPSG:3099',  'JGD2000 / Japan Plane Rectangular CS III'),
            ('EPSG:3100',  'JGD2000 / Japan Plane Rectangular CS IV'),
            ('EPSG:3101',  'JGD2000 / Japan Plane Rectangular CS V'),
            # ------------------------------------------------------------------
            # South America
            # ------------------------------------------------------------------
            ('EPSG:31978', 'SIRGAS 2000 / UTM zone 18S'),
            ('EPSG:31979', 'SIRGAS 2000 / UTM zone 19S'),
            ('EPSG:31980', 'SIRGAS 2000 / UTM zone 20S'),
            ('EPSG:31981', 'SIRGAS 2000 / UTM zone 21S'),
            ('EPSG:31982', 'SIRGAS 2000 / UTM zone 22S'),
            ('EPSG:31983', 'SIRGAS 2000 / UTM zone 23S'),
            ('EPSG:31984', 'SIRGAS 2000 / UTM zone 24S'),
            ('EPSG:31985', 'SIRGAS 2000 / UTM zone 25S'),
            ('EPSG:5641',  'SIRGAS 2000 / Brazil Polyconic'),
            ('EPSG:29168', 'SAD69 / UTM zone 18N'),
            ('EPSG:29169', 'SAD69 / UTM zone 19N'),
            ('EPSG:29178', 'SAD69 / UTM zone 18S'),
            ('EPSG:29179', 'SAD69 / UTM zone 19S'),
            ('EPSG:29183', 'SAD69 / UTM zone 23S'),
            ('EPSG:29184', 'SAD69 / UTM zone 24S'),
            ('EPSG:29185', 'SAD69 / UTM zone 25S'),
            # ------------------------------------------------------------------
            # Africa
            # ------------------------------------------------------------------
            ('EPSG:20137', 'Adindan / UTM zone 37N'),
            ('EPSG:20138', 'Adindan / UTM zone 38N'),
            ('EPSG:21036', 'Arc 1950 / UTM zone 36S'),
            ('EPSG:21037', 'Arc 1950 / UTM zone 37S'),
        ],
        'category': 'Project Details',
        'description': (
            'Coordinate Reference System for output shapefiles. Must be projected '
            '(meters), not geographic (lat/lon) — xmin, ymin, and Cell_size are '
            'always meters, so a geographic CRS would produce unusable output '
            'shapefiles. Only projected systems are listed — UTM, State Plane, '
            'national grids, etc.\n'
            'Type any part of the name or EPSG code to filter the list.\n'
            'Example: type "UTM 18N", "California", or "32618".'
        ),
    },
    {
        'key': 'notes',
        'label': 'Notes / Comments',
        'type': 'str',
        'default': '',
        'category': 'Project Details',
        'description': 'Optional notes or remarks about this model run.',
    },

    # =========================================================================
    # Triggering Event
    # =========================================================================
    {
        'key': 'Triggering_Indicator',
        'label': 'Triggering Mechanism',
        'type': 'choice',
        'default': '',
        'choices': [
            (1, 'Rainfall Only'),
            (2, 'Rainfall + Earthquake (Coupled)'),
        ],
        'category': 'Triggering Event',
        'description': (
            'Rainfall Only: slope instability driven solely by pore pressure changes.\n'
            'Coupled: combined rainfall and seismic triggering.'
        ),
    },

    # =========================================================================
    # Earthquake Inputs — only shown when Triggering_Indicator == 2
    # (Rainfall + Earthquake); the tab itself is hidden otherwise, so
    # individual fields below only need show_if for conditions *within*
    # this tab (e.g. which seismic model is selected)
    # =========================================================================
    {
        'key': 'earthquake_note',
        'type': 'note',
        'category': 'Earthquake Inputs',
        'text': [
            ('Everything on this tab applies only when Triggering Mechanism = '
             '"Rainfall + Earthquake (Coupled)" on the Triggering Event tab.', None),
        ],
    },
    {
        'key': 'Seismic_displacement_model',
        'label': 'Seismic Displacement Model',
        'type': 'choice',
        'default': '',
        'choices': [
            (1, 'Jibson (2007) — Rigid Block'),
            (2, 'Rathje et al. (2014) — Rigid Block'),
            (3, 'Rathje & Antonakos (2011) — Flexible / Decoupled'),
            (4, 'Bray & Macedo (2019) — Flexible Coupled'),
        ],
        'category': 'Earthquake Inputs',
        'description': (
            '- Jibson (2007) rigid block model\n'
            '- Rathje et al. (2014) Rigid block model\n'
            '- Rathje and Antonakos (2011) Decoupled flexible model\n'
            '- Bray and Macedo (2019) Coupled flexible model'
        ),
    },
    {
        'key': 'Rathje_method',
        'label': 'Rathje Ground Motion Intensity Measure',
        'type': 'choice',
        'default': '',
        'choices': [
            (1, 'PGAM — PGA + Moment Magnitude'),
            (2, 'PGAV — PGA + PGV'),
        ],
        'category': 'Earthquake Inputs',
        'description': (
            'Sub-method for the Rathje et al. (2014) Rigid and Rathje & Antonakos (2011) Flexible models.\n\n'
            'PGAM: displacement regressed on critical acceleration / PGA and moment magnitude — requires PGA and moment magnitude only.\n'
            'PGAV: displacement regressed on critical acceleration / PGA and PGV — requires the PGV raster.'
        ),
        'show_if': [
            {'param': 'Seismic_displacement_model', 'value': 2},
            {'param': 'Seismic_displacement_model', 'value': 3},
        ],
    },

    # =========================================================================
    # Topography
    # =========================================================================
    {
        'key': 'topography_note',
        'type': 'note',
        'category': 'Topography',
        'text': [
            ('The DEM must be provided in HDF5 format (.h5) or as a GeoTIFF '
             '(.tif/.tiff). Check the ReadMe file on how to generate a .h5 '
             'file from a 2D array. A GeoTIFF DEM auto-fills Cell_size, xmin, '
             'and ymin below instead.', None),
        ],
    },
    {
        'key': 'dem_file',
        'label': 'Digital Elevation Model (m)',
        'type': 'file',
        'default': '',
        'category': 'Topography',
        'description': (
            'HDF5 (.h5) or GeoTIFF (.tif/.tiff) file containing the Digital '
            'Elevation Model (meters). A GeoTIFF DEM auto-fills Cell_size, '
            'xmin, and ymin below from its embedded geotransform, instead of '
            'requiring them to be typed in by hand.'
        ),
        'file_filter': 'HDF5 or GeoTIFF files (*.h5 *.tif *.tiff)',
        'required': True,
    },
    {
        'key': 'Cell_size',
        'label': 'Grid Cell Size (m)',
        'type': 'float',
        'default': '',
        'category': 'Topography',
        'description': (
            'DEM grid resolution in x and y directions (meters).'
        ),
        'required': True,
    },
    {
        'key': 'xmin',
        'label': 'Lower-Left Corner Easting — xmin (m)',
        'type': 'float',
        'default': '',
        'category': 'Topography',
        'description': (
            'Easting (x) coordinate of the center of the lower-left DEM cell '
            '(meters). This is the left edge of the domain.'
        ),
        'required': True,
    },
    {
        'key': 'ymin',
        'label': 'Lower-Left Corner Northing — ymin (m)',
        'type': 'float',
        'default': '',
        'category': 'Topography',
        'description': (
            'Northing (y) coordinate of the center of the lower-left DEM cell '
            '(meters). This is the bottom edge of the domain.'
        ),
        'required': True,
    },

    # =========================================================================
    # Earthquake Inputs (continued) — PGA / PGV rasters
    # =========================================================================
    {
        'key': 'pga_note',
        'type': 'note',
        'category': 'Earthquake Inputs',
        'height': 1,
        'text': [
            ('The PGA raster must be provided as an HDF5 file (.h5).', None),
        ],
    },
    {
        'key': 'pga_file',
        'label': 'Peak Ground Acceleration — PGA (g)',
        'type': 'file',
        'default': '',
        'category': 'Earthquake Inputs',
        'description': (
            'Must be provided as an HDF5 file (.h5) containing the 2D Peak Ground\n'
            'Acceleration raster (units: g).\n'
            'Required when Triggering Mechanism = Rainfall + Earthquake.'
        ),
        'file_filter': 'HDF5 files (*.h5)',
    },
    {
        'key': 'pgv_note',
        'type': 'note',
        'category': 'Earthquake Inputs',
        'height': 1,
        'show_if': [
            {'param': 'Rathje_method',              'value': 2},
            {'param': 'Seismic_displacement_model', 'value': 4},
        ],
        'text': [
            ('The PGV raster must be provided as an HDF5 file (.h5) with values in cm/s.', None),
        ],
    },
    {
        'key': 'pgv_file',
        'label': 'Peak Ground Velocity — PGV (cm/s)',
        'type': 'file',
        'default': '',
        'category': 'Earthquake Inputs',
        'description': (
            'HDF5 file (.h5) containing the 2D Peak Ground Velocity raster (units: cm/s).\n'
            'Required for Rathje PGAV and Bray & Macedo models.'
        ),
        'file_filter': 'HDF5 files (*.h5)',
        'show_if': [
            {'param': 'Rathje_method',              'value': 2},
            {'param': 'Seismic_displacement_model', 'value': 4},
        ],
    },
    # =========================================================================
    # Scalar Inputs
    # =========================================================================
    {
        'key': 'time_points',
        'label': 'Number of Time Points',
        'type': 'int',
        'default': '',
        'category': 'Scalar Inputs',
        'description': (
            'Total number of time points to simulate (t = 0 to time_points − 1).\n\n'
            'Each time point corresponds to one interval in the storm time series — for example, '
            '1 hour, 30 minutes, or any other duration depending on how the user defines the '
            'temporal resolution of the input hydrological model. The duration of each time point '
            'does not affect the stability calculations.\n\n'
            'Must match the number of time steps found in the pore pressure directory. '
            'If this does not match, an error will be shown and the directory will be cleared.\n\n'
            'With a constant Ru, this is not enforced, but consider setting it to 1 — a constant Ru '
            'has no temporal variability, so every time step would produce an identical result. '
            'Selecting Ru with this not equal to 1 shows a warning as a reminder.'
        ),
    },
    {
        'key': 'Depth_points',
        'label': 'Number of Subsurface Layers',
        'type': 'int',
        'default': '',
        'category': 'Scalar Inputs',
        'description': (
            'Number of subsurface depth layers, discretizing the domain between z_min '
            'and z_max.\n'
            'Must match the layering of the hydrological model output files when using '
            'variable pore pressure files.\n'
            'Required even with a constant Ru (Hydrological_model_indicator = 0).\n'
            'Is one layer enough? The code will run, but every triggering cell will fail '
            'at exactly the same depth, since there is no depth variation to search over.'
        ),
    },
    {
        'key': 'z_min',
        'label': 'Minimum Depth Below Surface (m)',
        'type': 'float',
        'default': '',
        'category': 'Scalar Inputs',
        'description': (
            'Minimum depth from the surface: either 0 if exactly at the surface, or the '
            'center of the uppermost layer. Must be consistent with the hydrological '
            'model\'s discretization if you use an external hydrological model (variable '
            'pore pressure files) — if you use a constant Ru instead, it\'s up to you.'
        ),
    },
    {
        'key': 'z_max',
        'label': 'Maximum Depth Below Surface (m)',
        'type': 'float',
        'default': '',
        'category': 'Scalar Inputs',
        'description': (
            'Deepest depth you want to study: either the bottom edge of the last layer, '
            'or the center of the last layer. Must be consistent with the hydrological '
            'model\'s discretization if you use an external hydrological model (variable '
            'pore pressure files) — if you use a constant Ru instead, it\'s up to you.'
        ),
    },
    {
        'key': 'Min_LD_area',
        'label': 'Minimum Landslide Area to Model (m²)',
        'type': 'float',
        'default': '',
        'category': 'Scalar Inputs',
        'description': 'Landslides with an area smaller than this value are filtered out of the results.',
    },
    {
        'key': 'top_or_bottom_indicator',
        'label': 'Failure Depth Selection',
        'type': 'choice',
        'default': '',
        'choices': [
            (0, 'Shallowest Failing Depth'),
            (1, 'Deepest Failing Depth'),
        ],
        'category': 'Scalar Inputs',
        'description': (
            'When multiple depth layers fail at a cell, which depth defines\n'
            'the triggering surface used for the pseudo-3D landslide geometry.'
        ),
    },
    {
        'key': 'Gamma',
        'label': 'Unit Weight of Material γ (kN/m³)',
        'type': 'float',
        'default': '',
        'category': 'Scalar Inputs',
        'description': 'Total unit weight of the soil or rock material (kN/m³).',
    },
    {
        'key': 'Earthquake_time_point',
        'label': 'Earthquake Time Point',
        'type': 'int',
        'default': '',
        'category': 'Earthquake Inputs',
        'description': 'Time point at which the earthquake occurs. Must be an integer between 0 and (Number of Time Points − 1).',
    },
    {
        'key': 'Seismic_displacement_threshold',
        'label': 'Seismic Displacement Threshold (cm)',
        'type': 'float',
        'default': '',
        'category': 'Earthquake Inputs',
        'description': (
            'Newmark displacement threshold (cm) above which a cell is\n'
            'considered seismically triggered (Jibson 2007 model).'
        ),
    },
    {
        'key': 'M',
        'label': 'Earthquake Moment Magnitude Mw',
        'type': 'float',
        'default': '',
        'category': 'Earthquake Inputs',
        'description': 'Moment magnitude used in seismic displacement equations.',
    },
    {
        'key': 'Ts',
        'label': 'Site Fundamental Period Ts (s)',
        'type': 'float',
        'default': '',
        'category': 'Earthquake Inputs',
        'description': (
            'Fundamental period of the sliding mass (seconds).\n'
            'Required for Rathje Flexible and Bray & Macedo models.\n'
            'Use Ts = 0 for rigid-block assumption.'
        ),
        'show_if': [
            {'param': 'Seismic_displacement_model', 'value': 3},
            {'param': 'Seismic_displacement_model', 'value': 4},
        ],
    },
    {
        'key': 'fault_corners_note',
        'type': 'note',
        'category': 'Earthquake Inputs',
        'height': 3,
        'show_if': [
            {'param': 'Seismic_displacement_model', 'value': 3},
            {'param': 'Seismic_displacement_model', 'value': 4},
        ],
        'text': [
            ('Fault rupture plane — enter the four corner coordinates in the same '
             'projected CRS as the DEM (X and Y in meters, Z in meters depth '
             'positive downward, so the surface is Z = 0 and a 15 km deep corner '
             'is Z = 15 000 m). '
             'Corners must follow a consistent winding order: '
             'top-left → top-right → bottom-right → bottom-left '
             '(top = shallow edge, bottom = deep edge).', None),
        ],
    },
    {
        'key': 'fault_X1', 'label': 'Corner 1 — X, top-left (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Easting of the top-left fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Y1', 'label': 'Corner 1 — Y, top-left (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Northing of the top-left fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Z1', 'label': 'Corner 1 — Depth Z, top-left (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Depth of the top-left fault corner (meters, positive downward; surface = 0, e.g. 15 000 for 15 km depth).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_X2', 'label': 'Corner 2 — X, top-right (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Easting of the top-right fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Y2', 'label': 'Corner 2 — Y, top-right (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Northing of the top-right fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Z2', 'label': 'Corner 2 — Depth Z, top-right (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Depth of the top-right fault corner (meters, positive downward; surface = 0, e.g. 15 000 for 15 km depth).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_X3', 'label': 'Corner 3 — X, bottom-right (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Easting of the bottom-right fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Y3', 'label': 'Corner 3 — Y, bottom-right (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Northing of the bottom-right fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Z3', 'label': 'Corner 3 — Depth Z, bottom-right (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Depth of the bottom-right fault corner (meters, positive downward; surface = 0, e.g. 15 000 for 15 km depth).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_X4', 'label': 'Corner 4 — X, bottom-left (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Easting of the bottom-left fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Y4', 'label': 'Corner 4 — Y, bottom-left (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Northing of the bottom-left fault corner (meters).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },
    {
        'key': 'fault_Z4', 'label': 'Corner 4 — Depth Z, bottom-left (m)',
        'type': 'float', 'default': '', 'category': 'Earthquake Inputs',
        'description': 'Depth of the bottom-left fault corner (meters, positive downward; surface = 0, e.g. 15 000 for 15 km depth).',
        'show_if': [{'param': 'Seismic_displacement_model', 'value': 3},
                    {'param': 'Seismic_displacement_model', 'value': 4}],
    },

    # =========================================================================
    # Hydrological Formulations
    # =========================================================================
    {
        'key': 'Hydrological_model_indicator',
        'label': 'Pore Pressure Heads Model',
        'type': 'choice',
        'default': '',
        'choices': [
            (0, 'Constant Pore Pressure Coefficient (Ru)'),
            (1, 'Geospatially and Temporally Variable Pore Pressure Heads from External Hydrological Model'),
        ],
        'category': 'Hydrological Formulations',
        'widget_width': 560,
        'description': (
            'Constant Ru: a uniform pore pressure ratio applied across the entire domain and all time points.\n\n'
            'Variable: geospatially and temporally distributed pore pressure heads sourced from an external '
            'hydrological model, provided as HDF5 files named Pressure_head_T{t}Z{d+1}.h5 in the directory specified below.'
        ),
    },
    {
        'key': 'Ru',
        'label': 'Pore Pressure Ratio Ru',
        'type': 'float',
        'default': '',
        'category': 'Hydrological Formulations',
        'description': (
            'Constant pore pressure ratio (dimensionless). Ranges from 0 (dry) to '
            'Ru_max — not 1. Ru_max is the fully saturated condition (pore pressure '
            'head psi = depth z), which works out to Ru_max = gamma_water / gamma '
            '(soil unit weight) — always less than 1.\n'
            'Pressure head at depth z is psi(z) = Ru * gamma * z / gamma_water — Ru is '
            'a constant slope of how pressure grows with depth, so every cell at a given '
            'depth has the same psi, and it does not change over time (unlike variable '
            'pore pressure files). Depth still needs to be discretized via z_min/z_max/'
            'Depth_points — see those fields.\n'
            'Used only when Pore Pressure Model = Constant Ru.'
        ),
        'show_if': {'param': 'Hydrological_model_indicator', 'value': 0},
    },
    {
        'key': 'hydro_files_note',
        'type': 'note',
        'category': 'Hydrological Formulations',
        'show_if': {'param': 'Hydrological_model_indicator', 'value': 1},
        'text': [
            ('Pore pressure head files must be in HDF5 format (.h5) and named '
             'Pressure_head_T{t}Z{d+1}.h5, placed in the directory specified below. '
             'Each file is a 2D raster of pore pressure head at that time step and depth layer.', None),
        ],
    },
    {
        'key': 'hydro_files_dir',
        'label': 'Pore Pressure Files Directory',
        'type': 'dir',
        'default': '',
        'category': 'Hydrological Formulations',
        'description': (
            'Folder containing time- and depth-varying HDF5 pore pressure head files.\n'
            'Files must be named Pressure_head_T{t}Z{d+1}.h5.'
        ),
        'show_if': {'param': 'Hydrological_model_indicator', 'value': 1},
    },
    {
        'key': 'Strength_variation_with_theta',
        'label': 'Account for Shear Strength Variation with Saturation Level?',
        'type': 'choice',
        'default': '',
        'choices': [
            (0, "No — Fully saturated assumption, Bishop's effective stress coefficient χ = 1"),
            (1, "Yes — Bishop's effective stress coefficient varies with degree of saturation"),
        ],
        'category': 'Hydrological Formulations',
        'widget_width': 560,
        'label_width': 55,
        'description': (
            'No: fully saturated assumption — Bishop\'s effective stress coefficient χ = 1 everywhere.\n\n'
            'Yes: χ is interpolated between 0 (dry) and 1 (saturated) based on volumetric water content '
            '(requires θ_s, θ_r, and volumetric water content files).'
        ),
        'show_if': {'param': 'Hydrological_model_indicator', 'value': 1},
    },
    {
        'key': 'theta_files_note',
        'type': 'note',
        'category': 'Hydrological Formulations',
        'show_if': {'param': 'Strength_variation_with_theta', 'value': 1},
        'text': [
            ('Volumetric water content files must be in HDF5 format (.h5) '
             'and named Theta_T{t}Z{d+1}.h5. Each file is a 2D raster of volumetric water '
             'content at that time step and depth layer.', None),
        ],
    },
    {
        'key': 'theta_files_dir',
        'label': 'Volumetric Water Content Files Directory',
        'type': 'dir',
        'default': '',
        'category': 'Hydrological Formulations',
        'description': (
            'Folder containing time- and depth-varying volumetric water content\n'
            'HDF5 files. Files must be named Theta_T{t}Z{d+1}.h5.'
        ),
        'show_if': {'param': 'Strength_variation_with_theta', 'value': 1},
    },
    {
        'key': 'Theta_s',
        'label': 'Saturated Volumetric Water Content θ_s',
        'type': 'float',
        'default': '',
        'category': 'Hydrological Formulations',
        'description': 'Saturated volumetric water content (dimensionless, 0–1).',
        'show_if': {'param': 'Strength_variation_with_theta', 'value': 1},
    },
    {
        'key': 'Theta_r',
        'label': 'Residual Volumetric Water Content θ_r',
        'type': 'float',
        'default': '',
        'category': 'Hydrological Formulations',
        'description': 'Residual volumetric water content (dimensionless, 0–1).',
        'show_if': {'param': 'Strength_variation_with_theta', 'value': 1},
    },

    # =========================================================================
    # Shear Strength
    # =========================================================================
    {
        'key': 'Strength_status',
        'label': 'Shear Strength Distribution',
        'type': 'choice',
        'default': '',
        'choices': [
            (0, 'Uniform — Constant c and φ'),
            (1, 'Spatially Variable — 3D HDF5 Arrays'),
        ],
        'category': 'Shear Strength',
        'description': (
            'Uniform: same cohesion and friction angle applied everywhere.\n'
            'Spatially Variable: values read from 3D HDF5 arrays (rows × cols × depths).'
        ),
    },
    {
        'key': 'c',
        'label': 'Cohesion c (kPa)',
        'type': 'float',
        'default': '',
        'category': 'Shear Strength',
        'description': 'Uniform soil cohesion (kPa). Used when distribution = Uniform.',
        'show_if': {'param': 'Strength_status', 'value': 0},
    },
    {
        'key': 'Phi',
        'label': 'Friction Angle φ (degrees)',
        'type': 'float',
        'default': '',
        'category': 'Shear Strength',
        'description': 'Uniform soil friction angle (degrees). Used when distribution = Uniform.',
        'show_if': {'param': 'Strength_status', 'value': 0},
    },
    {
        'key': 'shear_strength_note',
        'type': 'note',
        'category': 'Shear Strength',
        'show_if': {'param': 'Strength_status', 'value': 1},
        'text': [
            ('Spatially variable cohesion and friction angle must each be provided '
             'as an HDF5 file (.h5) containing a 3D array shaped '
             '(rows × cols × depth layers), with values in kPa and degrees respectively.', None),
        ],
    },
    {
        'key': 'cohesion_3d_file',
        'label': 'Cohesion 3D Array File (.h5)',
        'type': 'file',
        'default': '',
        'category': 'Shear Strength',
        'description': (
            'HDF5 file containing a 3D cohesion array shaped\n'
            '(rows × cols × depth_points), values in kPa.'
        ),
        'file_filter': 'HDF5 files (*.h5)',
        'show_if': {'param': 'Strength_status', 'value': 1},
    },
    {
        'key': 'phi_3d_file',
        'label': 'Friction Angle 3D Array File (.h5)',
        'type': 'file',
        'default': '',
        'category': 'Shear Strength',
        'description': (
            'HDF5 file containing a 3D friction angle array shaped\n'
            '(rows × cols × depth_points), values in degrees.'
        ),
        'file_filter': 'HDF5 files (*.h5)',
        'show_if': {'param': 'Strength_status', 'value': 1},
    },
    # =========================================================================
    # Back-Analysis (BA) — Raster Inputs
    # =========================================================================
    # Keys are prefixed with 'ba_' (for back-analysis) so they can coexist
    # alongside the identically-named forward-analysis parameters in the GUI.
    # The GUI strips this prefix before passing values to back_analysis.run_model().
    {
        'key': 'raster_note_ba',
        'type': 'note',
        'category': 'BA Raster Inputs',
        'text': [
            ('The DEM must be provided in HDF5 format (.h5) or as a GeoTIFF '
             '(.tif/.tiff). Check the ReadMe file on how to generate a .h5 '
             'file from a 2D array. A GeoTIFF DEM auto-fills Cell_size, xmin, '
             'and ymin below instead.', None),
        ],
    },
    {
        'key': 'ba_dem_file',
        'label': 'Digital Elevation Model (m)',
        'type': 'file',
        'default': '',
        'category': 'BA Raster Inputs',
        'description': (
            'HDF5 (.h5) or GeoTIFF (.tif/.tiff) file containing the Digital '
            'Elevation Model (meters). A GeoTIFF DEM auto-fills ba_Cell_size, '
            'ba_xmin, and ba_ymin below from its embedded geotransform, '
            'instead of requiring them to be typed in by hand.'
        ),
        'file_filter': 'HDF5 or GeoTIFF files (*.h5 *.tif *.tiff)',
        'required': True,
    },
    {
        'key': 'ba_Cell_size',
        'label': 'Grid Cell Size (m)',
        'type': 'float',
        'default': '',
        'category': 'BA Raster Inputs',
        'description': (
            'DEM grid resolution in x and y directions (meters).'
        ),
        'required': True,
    },
    {
        'key': 'ba_xmin',
        'label': 'Lower-Left Corner Easting — xmin (m)',
        'type': 'float',
        'default': '',
        'category': 'BA Raster Inputs',
        'description': (
            'Easting (x) coordinate of the center of the lower-left DEM cell '
            '(meters). This is the left edge of the domain.'
        ),
        'required': True,
    },
    {
        'key': 'ba_ymin',
        'label': 'Lower-Left Corner Northing — ymin (m)',
        'type': 'float',
        'default': '',
        'category': 'BA Raster Inputs',
        'description': (
            'Northing (y) coordinate of the center of the lower-left DEM cell '
            '(meters). This is the bottom edge of the domain.'
        ),
        'required': True,
    },

    # =========================================================================
    # Back-Analysis (BA) — Hydrology
    # =========================================================================
    {
        'key': 'hydro_note_ba',
        'type': 'note',
        'category': 'BA Hydrology',
        'text': [
            ('Pore pressure head files must be in HDF5 format (.h5) and named '
             'Pressure_head_T{t}Z{d+1}.h5, placed in the directory specified below. '
             'Each file is a 2D raster of pore pressure head at that time step and depth layer.', None),
        ],
    },
    {
        'key': 'ba_hydro_files_dir',
        'label': 'Pore Pressure Files Directory',
        'type': 'dir',
        'default': '',
        'category': 'BA Hydrology',
        'description': (
            'Folder containing time- and depth-varying HDF5 pore pressure head files.\n'
            'Files must be named Pressure_head_T{t}Z{d+1}.h5.'
        ),
        'required': True,
    },
    {
        'key': 'ba_Strength_variation_with_theta',
        'label': 'Account for Shear Strength Variation with Saturation Level?',
        'type': 'choice',
        'default': '',
        'choices': [
            (0, "No — Fully saturated assumption, Bishop's effective stress coefficient χ = 1"),
            (1, "Yes — Bishop's effective stress coefficient varies with degree of saturation"),
        ],
        'category': 'BA Hydrology',
        'widget_width': 560,
        'label_width': 55,
        'description': (
            'No: fully saturated assumption — Bishop\'s χ = 1 everywhere.\n\n'
            'Yes: χ interpolated between 0 (dry) and 1 (saturated) based on volumetric water '
            'content (requires θ_s, θ_r, and volumetric water content files).'
        ),
    },
    {
        'key': 'theta_note_ba',
        'type': 'note',
        'category': 'BA Hydrology',
        'show_if': {'param': 'ba_Strength_variation_with_theta', 'value': 1},
        'text': [
            ('Volumetric water content files must be in HDF5 format (.h5) '
             'and named Theta_T{t}Z{d+1}.h5. Each file is a 2D raster of volumetric water '
             'content at that time step and depth layer.', None),
        ],
    },
    {
        'key': 'ba_theta_files_dir',
        'label': 'Volumetric Water Content Files Directory',
        'type': 'dir',
        'default': '',
        'category': 'BA Hydrology',
        'description': (
            'Folder containing HDF5 volumetric water content files.\n'
            'Files must be named Theta_T{t}Z{d+1}.h5.'
        ),
        'show_if': {'param': 'ba_Strength_variation_with_theta', 'value': 1},
    },
    {
        'key': 'ba_Theta_s',
        'label': 'Saturated Volumetric Water Content θ_s',
        'type': 'float',
        'default': '',
        'category': 'BA Hydrology',
        'description': 'Saturated volumetric water content (dimensionless, 0–1).',
        'show_if': {'param': 'ba_Strength_variation_with_theta', 'value': 1},
    },
    {
        'key': 'ba_Theta_r',
        'label': 'Residual Volumetric Water Content θ_r',
        'type': 'float',
        'default': '',
        'category': 'BA Hydrology',
        'description': 'Residual volumetric water content (dimensionless, 0–1).',
        'show_if': {'param': 'ba_Strength_variation_with_theta', 'value': 1},
    },

    # =========================================================================
    # Back-Analysis (BA) — Scalar Inputs
    # =========================================================================
    {
        'key': 'ba_z_min',
        'label': 'Minimum Depth Below Surface (m)',
        'type': 'float',
        'default': '',
        'category': 'BA Scalar Inputs',
        'description': (
            'Minimum depth from the surface: either 0 if exactly at the surface, or the '
            'center of the uppermost layer. Must be consistent with the hydrological '
            'model\'s discretization.'
        ),
    },
    {
        'key': 'ba_z_max',
        'label': 'Maximum Depth Below Surface (m)',
        'type': 'float',
        'default': '',
        'category': 'BA Scalar Inputs',
        'description': (
            'Deepest depth you want to study: either the bottom edge of the last layer, '
            'or the center of the last layer. Must be consistent with the hydrological '
            'model\'s discretization.'
        ),
    },
    {
        'key': 'ba_Depth_points',
        'label': 'Number of Subsurface Layers',
        'type': 'int',
        'default': '',
        'category': 'BA Scalar Inputs',
        'description': (
            'Number of subsurface depth layers, discretizing the domain between z_min '
            'and z_max.\n'
            'Must match the layering of the hydrological model output files.\n'
            'If this does not match the number of depth layers found in the pore pressure '
            'directory, an error will be shown and the directory will be cleared.'
        ),
    },
    {
        'key': 'ba_Time_points',
        'label': 'Number of Time Points',
        'type': 'int',
        'default': '',
        'category': 'BA Scalar Inputs',
        'description': (
            'Total number of time points in the simulation (t = 0 to Time_points − 1).\n\n'
            'Each time point corresponds to one interval in the storm time series. '
            'Must match the number of time steps found in the pore pressure directory.\n\n'
            'If this does not match the number of time steps found in the pore pressure '
            'directory, an error will be shown and the directory will be cleared.'
        ),
    },
    {
        'key': 'ba_R_search',
        'label': 'Search Radius Factor',
        'type': 'float',
        'default': '',
        'category': 'BA Scalar Inputs',
        'description': (
            'Dimensionless factor that controls the size of the search zone around each mapped landslide centroid.\n'
            'The search radius equals this factor multiplied by the square root of the mapped landslide area.\n'
            'Triggering cells within this radius are considered as candidates for the back-analysis.\n'
            'E.g., 1.2'
        ),
    },
    {
        'key': 'ba_Gamma_soil',
        'label': 'Unit Weight of Soil (kN/m3)',
        'type': 'float',
        'default': '',
        'category': 'BA Scalar Inputs',
        'description': 'Total unit weight of the soil or rock material (kN/m3).',
    },
    # =========================================================================
    # Back-Analysis (BA) — Shear Strength
    # =========================================================================
    {
        'key': 'strength_note_ba',
        'type': 'note',
        'category': 'BA Shear Strength',
        'text': [
            ('Specify the search range and increment for cohesion and friction angle. '
             'The back-analysis iterates over all combinations within these ranges '
             'to find the best match with each mapped landslide.', None),
        ],
    },
    {
        'key': 'ba_C_single_min',
        'label': 'Cohesion c — Minimum (kPa)',
        'type': 'float',
        'default': '',
        'category': 'BA Shear Strength',
        'description': 'Lower bound of the cohesion search range (kPa).',
    },
    {
        'key': 'ba_C_single_max',
        'label': 'Cohesion c — Maximum (kPa)',
        'type': 'float',
        'default': '',
        'category': 'BA Shear Strength',
        'description': 'Upper bound of the cohesion search range (kPa).',
    },
    {
        'key': 'ba_C_single_increment',
        'label': 'Cohesion c — Increment (kPa)',
        'type': 'float',
        'default': '',
        'category': 'BA Shear Strength',
        'description': 'Step size for cohesion iterations (kPa).',
    },
    {
        'key': 'ba_Phi_single_min',
        'label': 'Friction Angle φ — Minimum (degrees)',
        'type': 'float',
        'default': '',
        'category': 'BA Shear Strength',
        'description': 'Lower bound of the friction angle search range (degrees).',
    },
    {
        'key': 'ba_Phi_single_max',
        'label': 'Friction Angle φ — Maximum (degrees)',
        'type': 'float',
        'default': '',
        'category': 'BA Shear Strength',
        'description': 'Upper bound of the friction angle search range (degrees).',
    },
    {
        'key': 'ba_Phi_single_increment',
        'label': 'Friction Angle φ — Increment (degrees)',
        'type': 'float',
        'default': '',
        'category': 'BA Shear Strength',
        'description': 'Step size for friction angle iterations (degrees).',
    },
    # =========================================================================
    # Mapped Landslide Inventory
    # =========================================================================
    {
        'key': 'inventory_note_ba',
        'type': 'note',
        'category': 'Mapped Landslide Inventory',
        'height': 6,
        'text': [
            ('Two input files are required:\n'
             '  (i)   ID.xlsx — no header row; first column contains the integer landslide IDs, one per row.\n'
             '  (ii)  LD{ID}.xlsx — one file per landslide; row 1 must be a header row (any text — CRISIS reads '
             'by column position, not by the header text, but row 1 is always skipped, so if it\'s missing the '
             'first data row gets read as the header instead and the actual data is lost). Row 2 contains the '
             'corresponding values, in this order:\n'
             '           Mapped Area (m^2),  Mapped Centroid X (m),  Mapped Centroid Y (m),  Mapped Volume (m^3)\n'
             '        Centroid X/Y can be extracted directly from your mapped landslide polygons in GIS '
             'software (e.g. the centroid tool in QGIS/ArcGIS), in the same projected coordinate system used '
             'elsewhere in this model.', None),
        ],
    },
    {
        'key': 'ba_landslide_ids_file',
        'label': 'Landslide IDs File (ID.xlsx)',
        'type': 'file',
        'default': '',
        'category': 'Mapped Landslide Inventory',
        'description': (
            'Excel file (.xlsx) containing landslide IDs — no header, first column only.\n'
            'Each row is one integer landslide ID.'
        ),
        'file_filter': 'Excel files (*.xlsx)',
        'required': True,
    },
    {
        'key': 'ba_landslide_files_dir',
        'label': 'Individual Landslide Files Directory',
        'type': 'dir',
        'default': '',
        'category': 'Mapped Landslide Inventory',
        'description': (
            'Directory containing one Excel file per mapped landslide, named LD{ID}.xlsx.\n'
            'Row 1 must be a header row (any text — required, since row 1 is always skipped; without it '
            'the first data row is misread as the header). Row 2 is the one data row, in this column order '
            '(read by position, not by header text): Mapped Area (m^2), Mapped Centroid X (m), '
            'Mapped Centroid Y (m), Mapped Volume (m^3). Centroid X/Y can be extracted from GIS software '
            'using the same projected coordinate system as the rest of the model.'
        ),
        'required': True,
    },
    {
        'key': 'ba_mapped_ls_shapefile',
        'label': 'Mapped Landslides Shapefile',
        'type': 'file',
        'default': '',
        'category': 'Mapped Landslide Inventory',
        'description': (
            'Shapefile (.shp) of the mapped landslide inventory.\n'
            'Used to overlay mapped landslide outlines on the DEM in the Outputs tab.\n'
            'Must be in the same Coordinate Reference System (CRS) as the DEM.'
        ),
        'file_filter': 'Shapefiles (*.shp)',
        'required': False,
    },
]
