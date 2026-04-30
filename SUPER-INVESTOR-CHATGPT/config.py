import os
import json
import time
import requests as _req
from dotenv import load_dotenv

load_dotenv()


def _fetch_bist_dynamic():
    """Bigpara'dan BIST listesini çek. Başarısız olursa None döndür."""
    _cache_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(_cache_dir, exist_ok=True)
    _cache_file = os.path.join(_cache_dir, "bist_list_cache.json")
    if os.path.exists(_cache_file):
        try:
            with open(_cache_file) as _f:
                _cached = json.load(_f)
            if time.time() - _cached.get("ts", 0) < 86400 and len(_cached.get("tickers", [])) > 200:
                return _cached["tickers"]
        except Exception:
            pass
    try:
        _r = _req.get(
            "https://bigpara.hurriyet.com.tr/api/v1/hisse/list",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        _data = _r.json().get("data", [])
        _tickers = sorted(set(
            x["kod"].strip() for x in _data
            if x.get("kod", "").strip().isalpha() and 4 <= len(x.get("kod", "").strip()) <= 6
        ))
        if len(_tickers) > 200:
            try:
                with open(_cache_file, "w") as _f:
                    json.dump({"ts": time.time(), "tickers": _tickers}, _f)
            except Exception:
                pass
            return _tickers
    except Exception:
        pass
    return None

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

CACHE_TTL_HISTORY = 600
CACHE_TTL_QUOTE = 120

BIST_ALL_TICKERS = [
    "A1CAP", "A1YEN", "ACSEL", "ADEL", "ADESE", "ADGYO", "AEFES", "AFYON", "AGESA", "AGHOL",
    "AGROT", "AGYO", "AHGAZ", "AHSGY", "AKBNK", "AKCNS", "AKENR", "AKFGY", "AKFIS", "AKFYE",
    "AKGRT", "AKHAN", "AKMGY", "AKSA", "AKSEN", "AKSGY", "AKSUE", "AKYHO", "ALARK", "ALBRK",
    "ALCAR", "ALCTL", "ALFAS", "ALGYO", "ALKA", "ALKIM", "ALKLC", "ALTNY", "ALVES", "ANELE",
    "ANGEN", "ANHYT", "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA", "ARFYE", "ARMGD", "ARSAN",
    "ARTMS", "ARZUM", "ASELS", "ASGYO", "ASTOR", "ASUZU", "ATAGY", "ATAKP", "ATATP", "ATATR",
    "ATEKS", "ATLAS", "ATSYH", "AVGYO", "AVHOL", "AVOD", "AVPGY", "AVTUR", "AYCES", "AYDEM",
    "AYEN", "AYES", "AYGAZ", "AZTEK", "BAGFS", "BAHKM", "BAKAB", "BALAT", "BALSU", "BANVT",
    "BARMA", "BASCM", "BASGZ", "BAYRK", "BEGYO", "BERA", "BESLR", "BESTE", "BEYAZ", "BFREN",
    "BIENY", "BIGCH", "BIGEN", "BIGTK", "BIMAS", "BINBN", "BINHO", "BIOEN", "BIZIM", "BJKAS",
    "BLCYT", "BLUME", "BMSCH", "BMSTL", "BNTAS", "BOBET", "BORLS", "BORSK", "BOSSA", "BRISA",
    "BRKO", "BRKSN", "BRKVY", "BRLSM", "BRMEN", "BRSAN", "BRYAT", "BSOKE", "BTCIM", "BUCIM",
    "BULGS", "BURCE", "BURVA", "BVSAN", "BYDNR", "CANTE", "CASA", "CATES", "CCOLA", "CELHA",
    "CEMAS", "CEMTS", "CEMZY", "CEOEM", "CGCAM", "CIMSA", "CLEBI", "CMBTN", "CMENT", "CONSE",
    "COSMO", "CRDFA", "CRFSA", "CUSAN", "CVKMD", "CWENE", "DAGI", "DAPGM", "DARDL", "DCTTR",
    "DENGE", "DERHL", "DERIM", "DESA", "DESPC", "DEVA", "DGATE", "DGGYO", "DGNMO", "DIRIT",
    "DITAS", "DMRGD", "DMSAS", "DNISI", "DOAS", "DOCO", "DOFER", "DOFRB", "DOGUB", "DOHOL",
    "DOKTA", "DSTKF", "DUNYH", "DURDO", "DURKN", "DYOBY", "DZGYO", "EBEBK", "ECILC", "ECOGR",
    "ECZYT", "EDATA", "EDIP", "EFOR", "EGEEN", "EGEGY", "EGEPO", "EGGUB", "EGPRO", "EGSER",
    "EKGYO", "EKIZ", "EKOS", "EKSUN", "ELITE", "EMKEL", "EMNIS", "EMPAE", "ENDAE", "ENERY",
    "ENJSA", "ENKAI", "ENSRI", "ENTRA", "EPLAS", "ERBOS", "ERCB", "EREGL", "ERSU", "ESCAR",
    "ESCOM", "ESEN", "ETILR", "ETYAT", "EUHOL", "EUKYO", "EUPWR", "EUREN", "EUYO", "EYGYO",
    "FADE", "FENER", "FLAP", "FMIZP", "FONET", "FORMT", "FORTE", "FRIGO", "FRMPL", "FROTO",
    "FZLGY", "GARAN", "GARFA", "GATEG", "GEDIK", "GEDZA", "GENIL", "GENKM", "GENTS", "GEREL",
    "GESAN", "GIPTA", "GLBMD", "GLCVY", "GLRMK", "GLRYH", "GLYHO", "GMTAS", "GOKNR", "GOLTS",
    "GOODY", "GOZDE", "GRNYO", "GRSEL", "GRTHO", "GSDDE", "GSDHO", "GSRAY", "GUBRF", "GUNDG",
    "GWIND", "GZNMI", "HALKB", "HATEK", "HATSN", "HDFGS", "HEDEF", "HEKTS", "HKTM", "HLGYO",
    "HOROZ", "HRKET", "HTTBT", "HUBVC", "HUNER", "HURGZ", "ICBCT", "ICUGS", "IDGYO", "IEYHO",
    "IHAAS", "IHEVA", "IHGZT", "IHLAS", "IHLGM", "IHYAY", "IMASM", "INDES", "INFO", "INGRM",
    "INTEK", "INTEM", "INVEO", "INVES", "ISATR", "ISBIR", "ISBTR", "ISCTR", "ISDMR", "ISFIN",
    "ISGSY", "ISGYO", "ISKPL", "ISKUR", "ISMEN", "ISSEN", "ISYAT", "IZENR", "IZFAS", "IZINV",
    "IZMDC", "JANTS", "KAPLM", "KAREL", "KARSN", "KARTN", "KATMR", "KAYSE", "KBORU", "KCAER",
    "KCHOL", "KENT", "KERVN", "KFEIN", "KGYO", "KIMMR", "KLGYO", "KLKIM", "KLMSN", "KLNMA",
    "KLRHO", "KLSER", "KLSYN", "KLYPV", "KMPUR", "KNFRT", "KOCMT", "KONKA", "KONTR", "KONYA",
    "KOPOL", "KORDS", "KOTON", "KRDMA", "KRDMB", "KRDMD", "KRGYO", "KRONT", "KRPLS", "KRSTL",
    "KRTEK", "KRVGD", "KSTUR", "KTLEV", "KTSKR", "KUTPO", "KUVVA", "KUYAS", "KZBGY", "KZGYO",
    "LIDER", "LIDFA", "LILAK", "LINK", "LKMNH", "LMKDC", "LOGO", "LRSHO", "LUKSK", "LXGYO",
    "LYDHO", "LYDYE", "MAALT", "MACKO", "MAGEN", "MAKIM", "MAKTK", "MANAS", "MARBL", "MARKA",
    "MARMR", "MARTI", "MAVI", "MCARD", "MEDTR", "MEGAP", "MEGMT", "MEKAG", "MEPET", "MERCN",
    "MERIT", "MERKO", "METRO", "MEYSU", "MGROS", "MHRGY", "MIATK", "MMCAS", "MNDRS", "MNDTR",
    "MOBTL", "MOGAN", "MOPAS", "MPARK", "MRGYO", "MRSHL", "MSGYO", "MTRKS", "MTRYO", "MZHLD",
    "NATEN", "NETAS", "NETCD", "NIBAS", "NTGAZ", "NTHOL", "NUGYO", "NUHCM", "OBAMS", "OBASE",
    "ODAS", "ODINE", "OFSYM", "ONCSM", "ONRYT", "ORCAY", "ORGE", "ORMA", "OSMEN", "OSTIM",
    "OTKAR", "OTTO", "OYAKC", "OYAYO", "OYLUM", "OYYAT", "OZATD", "OZGYO", "OZKGY", "OZRDN",
    "OZSUB", "OZYSR", "PAGYO", "PAHOL", "PAMEL", "PAPIL", "PARSN", "PASEU", "PATEK", "PCILT",
    "PEKGY", "PENGD", "PENTA", "PETKM", "PETUN", "PGSUS", "PINSU", "PKART", "PKENT", "PLTUR",
    "PNLSN", "PNSUT", "POLHO", "POLTK", "PRDGS", "PRKAB", "PRKME", "PRZMA", "PSDTC", "PSGYO",
    "QNBFK", "QNBTR", "QUAGR", "RALYH", "RAYSG", "REEDR", "RGYAS", "RNPOL", "RODRG", "RTALB",
    "RUBNS", "RUZYE", "RYGYO", "RYSAS", "SAFKR", "SAHOL", "SAMAT", "SANEL", "SANFM", "SANKO",
    "SARKY", "SASA", "SAYAS", "SDTTR", "SEGMN", "SEGYO", "SEKFK", "SEKUR", "SELEC", "SELVA",
    "SERNT", "SEYKM", "SILVR", "SISE", "SKBNK", "SKTAS", "SKYLP", "SKYMD", "SMART", "SMRTG",
    "SMRVA", "SNGYO", "SNICA", "SNPAM", "SODSN", "SOKE", "SOKM", "SONME", "SRVGY", "SUMAS",
    "SUNTK", "SURGY", "SUWEN", "SVGYO", "TABGD", "TARKM", "TATEN", "TATGD", "TAVHL", "TBORG",
    "TCELL", "TCKRC", "TDGYO", "TEHOL", "TEKTU", "TERA", "TEZOL", "TGSAS", "THYAO", "TKFEN",
    "TKNSA", "TLMAN", "TMPOL", "TMSN", "TNZTP", "TOASO", "TRALT", "TRCAS", "TRENJ", "TRGYO",
    "TRHOL", "TRILC", "TRMET", "TSGYO", "TSKB", "TSPOR", "TTKOM", "TTRAK", "TUCLK", "TUKAS",
    "TUPRS", "TUREX", "TURGG", "TURSG", "UCAYM", "UFUK", "ULAS", "ULKER", "ULUFA", "ULUSE",
    "ULUUN", "UMPAS", "UNLU", "USAK", "VAKBN", "VAKFA", "VAKFN", "VAKKO", "VANGD", "VBTYZ",
    "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO", "VKGYO", "VKING", "VRGYO", "VSNMD", "YAPRK",
    "YATAS", "YAYLA", "YBTAS", "YEOTK", "YESIL", "YGGYO", "YGYO", "YIGIT", "YKBNK", "YKSLN",
    "YONGA", "YUNSA", "YYAPI", "YYLGD", "ZEDUR", "ZERGY", "ZGYO", "ZOREN", "ZRGYO",
]

USA_ALL_TICKERS = [
    "A", "AA", "AAL", "AAON", "AAPL", "ABBV", "ABNB", "ABT", "ACGL", "ACI",
    "ACM", "ACN", "ADBE", "ADC", "ADI", "ADM", "ADP", "ADSK", "AEE", "AEIS",
    "AEP", "AES", "AFG", "AFL", "AGCO", "AHR", "AIG", "AIT", "AIZ", "AJG",
    "AKAM", "ALB", "ALGM", "ALGN", "ALK", "ALL", "ALLE", "ALLY", "ALV", "AM",
    "AMAT", "AMCR", "AMD", "AME", "AMG", "AMGN", "AMH", "AMKR", "AMP", "AMT",
    "AMZN", "AN", "ANET", "ANF", "AON", "AOS", "APA", "APD", "APG", "APH",
    "APO", "APP", "APPF", "APTV", "AR", "ARE", "ARES", "ARMK", "ARW", "ARWR",
    "ASB", "ASH", "ATI", "ATO", "ATR", "AVAV", "AVB", "AVGO", "AVNT", "AVT",
    "AVTR", "AVY", "AWK", "AXON", "AXP", "AXTA", "AYI", "AZO", "BA", "BAC",
    "BAH", "BALL", "BAX", "BBWI", "BBY", "BC", "BCO", "BDC", "BDX", "BEN",
    "BF.B", "BG", "BHF", "BIIB", "BILL", "BIO", "BJ", "BK", "BKH", "BKNG",
    "BKR", "BLD", "BLDR", "BLK", "BLKB", "BMRN", "BMY", "BR", "BRBR", "BRK.B",
    "BRKR", "BRO", "BROS", "BRX", "BSX", "BSY", "BURL", "BWA", "BWXT", "BX",
    "BXP", "BYD", "C", "CACI", "CAG", "CAH", "CAR", "CARR", "CART", "CASY",
    "CAT", "CAVA", "CB", "CBOE", "CBRE", "CBSH", "CBT", "CCI", "CCK", "CCL",
    "CDNS", "CDP", "CDW", "CEG", "CELH", "CF", "CFG", "CFR", "CG", "CGNX",
    "CHD", "CHDN", "CHE", "CHH", "CHRD", "CHRW", "CHTR", "CHWY", "CI", "CIEN",
    "CINF", "CL", "CLF", "CLH", "CLX", "CMC", "CMCSA", "CME", "CMG", "CMI",
    "CMS", "CNC", "CNH", "CNM", "CNO", "CNP", "CNX", "CNXC", "COF", "COHR",
    "COIN", "COKE", "COLB", "COLM", "COO", "COP", "COR", "COST", "COTY", "CPAY",
    "CPB", "CPRI", "CPRT", "CPT", "CR", "CRBG", "CRH", "CRL", "CRM", "CROX",
    "CRS", "CRUS", "CRWD", "CSCO", "CSGP", "CSL", "CSX", "CTAS", "CTRA", "CTRE",
    "CTSH", "CTVA", "CUBE", "CUZ", "CVLT", "CVNA", "CVS", "CVX", "CW", "CXT",
    "CYTK", "D", "DAL", "DAR", "DASH", "DBX", "DCI", "DD", "DDOG", "DE",
    "DECK", "DELL", "DG", "DGX", "DHI", "DHR", "DINO", "DIS", "DKS", "DLB",
    "DLR", "DLTR", "DOC", "DOCS", "DOCU", "DOV", "DOW", "DPZ", "DRI", "DT",
    "DTE", "DTM", "DUK", "DUOL", "DVA", "DVN", "DXCM", "DY", "EA", "EBAY",
    "ECL", "ED", "EEFT", "EFX", "EG", "EGP", "EHC", "EIX", "EL", "ELAN",
    "ELF", "ELS", "ELV", "EME", "EMR", "ENS", "ENSG", "ENTG", "EOG", "EPAM",
    "EPR", "EQH", "EQIX", "EQR", "EQT", "ERIE", "ES", "ESAB", "ESNT", "ESS",
    "ETN", "ETR", "EVR", "EVRG", "EW", "EWBC", "EXC", "EXE", "EXEL", "EXLS",
    "EXP", "EXPD", "EXPE", "EXPO", "EXR", "F", "FAF", "FANG", "FAST", "FBIN",
    "FCFS", "FCN", "FCX", "FDS", "FDX", "FE", "FFIN", "FFIV", "FHI", "FHN",
    "FICO", "FIS", "FISV", "FITB", "FIVE", "FIX", "FLEX", "FLG", "FLO", "FLR",
    "FLS", "FN", "FNB", "FND", "FNF", "FOUR", "FOX", "FOXA", "FR", "FRT",
    "FSLR", "FTI", "FTNT", "FTV", "G", "GAP", "GATX", "GBCI", "GD", "GDDY",
    "GE", "GEF", "GEHC", "GEN", "GEV", "GGG", "GHC", "GILD", "GIS", "GL",
    "GLPI", "GLW", "GM", "GME", "GMED", "GNRC", "GNTX", "GOOG", "GOOGL", "GPC",
    "GPK", "GPN", "GRMN", "GS", "GT", "GTLS", "GWRE", "GWW", "GXO", "H",
    "HAE", "HAL", "HALO", "HAS", "HBAN", "HCA", "HD", "HGV", "HIG", "HII",
    "HIMS", "HL", "HLI", "HLNE", "HLT", "HOG", "HOLX", "HOMB", "HON", "HOOD",
    "HPE", "HPQ", "HQY", "HR", "HRB", "HRL", "HSIC", "HST", "HSY", "HUBB",
    "HUM", "HWC", "HWM", "HXL", "IBKR", "IBM", "IBOC", "ICE", "IDA", "IDCC",
    "IDXX", "IEX", "IFF", "ILMN", "INCY", "INGR", "INTC", "INTU", "INVH", "IP",
    "IPGP", "IQV", "IR", "IRM", "IRT", "ISRG", "IT", "ITT", "ITW", "IVZ",
    "J", "JAZZ", "JBHT", "JBL", "JCI", "JEF", "JHG", "JKHY", "JLL", "JNJ",
    "JPM", "KBH", "KBR", "KD", "KDP", "KEX", "KEY", "KEYS", "KHC", "KIM",
    "KKR", "KLAC", "KMB", "KMI", "KNF", "KNSL", "KNX", "KO", "KR", "KRC",
    "KRG", "KTOS", "KVUE", "L", "LAD", "LAMR", "LDOS", "LEA", "LECO", "LEN",
    "LFUS", "LH", "LHX", "LII", "LIN", "LITE", "LIVN", "LLY", "LMT", "LNT",
    "LNTH", "LOPE", "LOW", "LPX", "LRCX", "LSCC", "LSTR", "LULU", "LUV", "LVS",
    "LYB", "LYV", "M", "MA", "MAA", "MANH", "MAR", "MAS", "MASI", "MAT",
    "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MEDP", "MET", "META", "MGM",
    "MIDD", "MKC", "MKSI", "MLI", "MLM", "MMM", "MMS", "MNST", "MO", "MOG.A",
    "MORN", "MOS", "MP", "MPC", "MPWR", "MRK", "MRNA", "MRSH", "MS", "MSA",
    "MSCI", "MSFT", "MSI", "MSM", "MTB", "MTD", "MTDR", "MTG", "MTN", "MTSI",
    "MTZ", "MU", "MUR", "MUSA", "MZTI", "NBIX", "NCLH", "NDAQ", "NDSN", "NEE",
    "NEM", "NEU", "NFG", "NFLX", "NI", "NJR", "NKE", "NLY", "NNN", "NOC",
    "NOV", "NOVT", "NOW", "NRG", "NSA", "NSC", "NTAP", "NTNX", "NTRS", "NUE",
    "NVDA", "NVR", "NVST", "NVT", "NWE", "NWS", "NWSA", "NXPI", "NXST", "NXT",
    "NYT", "O", "OC", "ODFL", "OGE", "OGS", "OHI", "OKE", "OKTA", "OLED",
    "OLLI", "OLN", "OMC", "ON", "ONB", "ONTO", "OPCH", "ORA", "ORCL", "ORI",
    "ORLY", "OSK", "OTIS", "OVV", "OXY", "OZK", "PAG", "PANW", "PATH", "PAYX",
    "PB", "PBF", "PCAR", "PCG", "PCTY", "PEG", "PEGA", "PEN", "PEP", "PFE",
    "PFG", "PFGC", "PG", "PGR", "PH", "PHM", "PII", "PINS", "PK", "PKG",
    "PLD", "PLNT", "PLTR", "PM", "PNC", "PNFP", "PNR", "PNW", "PODD", "POOL",
    "POR", "POST", "PPC", "PPG", "PPL", "PR", "PRI", "PRU", "PSA", "PSKY",
    "PSN", "PSTG", "PSX", "PTC", "PVH", "PWR", "PYPL", "Q", "QCOM", "QLYS",
    "R", "RBA", "RBC", "RCL", "REG", "REGN", "REXR", "RF", "RGA", "RGEN",
    "RGLD", "RH", "RJF", "RL", "RLI", "RMBS", "RMD", "RNR", "ROIV", "ROK",
    "ROL", "ROP", "ROST", "RPM", "RRC", "RRX", "RS", "RSG", "RTX", "RVTY",
    "RYAN", "RYN", "SAIA", "SAIC", "SAM", "SARO", "SATS", "SBAC", "SBRA", "SBUX",
    "SCHW", "SCI", "SEIC", "SF", "SFM", "SGI", "SHC", "SHW", "SIGI", "SITM",
    "SJM", "SLAB", "SLB", "SLGN", "SLM", "SMCI", "SMG", "SNA", "SNDK", "SNPS",
    "SNX", "SO", "SOLS", "SOLV", "SON", "SPG", "SPGI", "SPXC", "SR", "SRE",
    "SSB", "SSD", "ST", "STAG", "STE", "STLD", "STRL", "STT", "STWD", "STX",
    "STZ", "SW", "SWK", "SWKS", "SWX", "SYF", "SYK", "SYNA", "SYY", "T",
    "TAP", "TCBI", "TDG", "TDY", "TECH", "TEL", "TER", "TEX", "TFC", "TGT",
    "THC", "THG", "THO", "TJX", "TKO", "TKR", "TLN", "TMHC", "TMO", "TMUS",
    "TNL", "TOL", "TPL", "TPR", "TREX", "TRGP", "TRMB", "TROW", "TRU", "TRV",
    "TSCO", "TSLA", "TSN", "TT", "TTC", "TTD", "TTEK", "TTMI", "TTWO", "TWLO",
    "TXN", "TXNM", "TXRH", "TXT", "TYL", "UAL", "UBER", "UBSI", "UDR", "UFPI",
    "UGI", "UHS", "ULS", "ULTA", "UMBF", "UNH", "UNM", "UNP", "UPS", "URI",
    "USB", "USFD", "UTHR", "V", "VAL", "VC", "VFC", "VICI", "VICR", "VLO",
    "VLTO", "VLY", "VMC", "VMI", "VNO", "VNOM", "VNT", "VOYA", "VRSK", "VRSN",
    "VRT", "VRTX", "VST", "VTR", "VTRS", "VVV", "VZ", "WAB", "WAL", "WAT",
    "WBD", "WBS", "WCC", "WDAY", "WDC", "WEC", "WELL", "WEX", "WFC", "WFRD",
    "WH", "WHR", "WING", "WLK", "WM", "WMB", "WMG", "WMS", "WMT", "WPC",
    "WRB", "WSM", "WSO", "WST", "WTFC", "WTRG", "WTS", "WTW", "WWD", "WY",
    "WYNN", "XEL", "XOM", "XPO", "XRAY", "XYL", "XYZ", "YETI", "YUM", "ZBH",
    "ZBRA", "ZION", "ZTS",
]

# Delisted / ETF / fon olduğu bilinen hisseler — havuzda istenmiyor
_EXCLUDED_BIST = {
    "KOZAL","KERVT","LYDIA","APGLD","ENRYA","GMSTRF","USDTRF","ZGOLDF",
    "GLDTR","GMSTR","USDTR","QTEMZ","APMDL","APBDL","APLIB",
    "ISGLK","NPTLR","OPTGY","OPTLR","ZGOLD",
}

# Dynamic BIST: mevcut statik liste + Bigpara'dan gelen dinamik liste (filtreli)
_dynamic_bist = _fetch_bist_dynamic()
if _dynamic_bist:
    _dynamic_bist = [t for t in _dynamic_bist if t not in _EXCLUDED_BIST]
    BIST_ALL_TICKERS = sorted(set(BIST_ALL_TICKERS) | set(_dynamic_bist))
BIST_ALL_TICKERS = [t for t in BIST_ALL_TICKERS if t not in _EXCLUDED_BIST]

SUPPORTED_MARKETS = {
    "BIST": {
        "label": "BIST (Türkiye)",
        "exchange": "BIST",
        "currency": "TRY",
        "symbols": BIST_ALL_TICKERS,
    },
    "USA": {
        "label": "ABD Hisseleri",
        "exchange": "NASDAQ/NYSE",
        "currency": "USD",
        "symbols": USA_ALL_TICKERS,
    },
}

BENCHMARK_INDEX = {
    "USA": "SPX",
    "BIST": "XU100",
}

BIST100_TICKERS = [
    "THYAO", "GARAN", "AKBNK", "EREGL", "BIMAS",
    "KCHOL", "SAHOL", "SISE", "TUPRS", "ASELS",
    "TCELL", "PGSUS", "TOASO", "FROTO", 
    "HEKTS", "MGROS", "TAVHL", "ARCLK", "SASA",
    "PETKM", "ISCTR", "YKBNK", "VAKBN", "HALKB",
    "TKFEN", "TTKOM", "EKGYO", "ENKAI", "GUBRF",
    "KRDMD", "OYAKC", "OTKAR", "DOHOL", "AEFES",
    "SOKM", "ALARK", "ECZYT", "CIMSA", "AKSEN",
    "GESAN", "KONTR", "BRYAT", "BTCIM", "ISGYO",
    "TSKB", "AGHOL", "CCOLA", "TTRAK", "ULKER",
    "MPARK", "INDES", "LOGO", "QUAGR", "BERA",
    "VERUS", "EUPWR", "KLSER", "PAPIL", "ARDYZ",
    "CWENE", "TURSG", "ISMEN", "ZOREN", "SARKY",
    "AYDEM", "ODAS", "BRSAN", "VESBE", "PENTA",
    "MAVI", "DOAS", "TMSN", "NETAS", "GLYHO",
    "ANHYT", "ANELE", "KCAER", "AHGAZ",
    "BIOEN", "EGEEN", "GEDZA", "GOODY", "KARTN",
    "KLRHO", "KUYAS", "MAGEN", "OZKGY", "SILVR",
    "TMPOL", "TUKAS", "YATAS", "ADEL", "VESTL",
    "AKFGY", "ALBRK", "ALFAS", "ANSGR", "ARSAN",
]

BIST_SEGMENTS = {
    "BISTTUM": "BIST TÜM",
    "BIST100": "BIST 100",
    "BIST100_DISI": "BIST 100 Dışı",
}

SP500_TICKERS = [
    "A", "AAPL", "ABBV", "ABNB", "ABT", "ACGL", "ACN", "ADBE", "ADI", "ADM",
    "ADP", "ADSK", "AEE", "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM",
    "ALB", "ALGN", "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP",
    "AMT", "AMZN", "ANET", "AON", "AOS", "APA", "APD", "APH", "APO", "APP",
    "APTV", "ARE", "ARES", "ATO", "AVB", "AVGO", "AVY", "AWK", "AXON", "AXP",
    "AZO", "BA", "BAC", "BALL", "BAX", "BBY", "BDX", "BEN", "BF.B", "BG",
    "BIIB", "BK", "BKNG", "BKR", "BLDR", "BLK", "BMY", "BR", "BRK.B", "BRO",
    "BSX", "BX", "BXP", "C", "CAG", "CAH", "CARR", "CAT", "CB", "CBOE",
    "CBRE", "CCI", "CCL", "CDNS", "CDW", "CEG", "CF", "CFG", "CHD", "CHRW",
    "CHTR", "CI", "CIEN", "CINF", "CL", "CLX", "CMCSA", "CME", "CMG", "CMI",
    "CMS", "CNC", "CNP", "COF", "COHR", "COIN", "COO", "COP", "COR", "COST",
    "CPAY", "CPB", "CPRT", "CPT", "CRH", "CRL", "CRM", "CRWD", "CSCO", "CSGP",
    "CSX", "CTAS", "CTRA", "CTSH", "CTVA", "CVNA", "CVS", "CVX", "D", "DAL",
    "DASH", "DD", "DDOG", "DE", "DECK", "DELL", "DG", "DGX", "DHI", "DHR",
    "DIS", "DLR", "DLTR", "DOC", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK",
    "DVA", "DVN", "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EG", "EIX",
    "EL", "ELV", "EME", "EMR", "EOG", "EPAM", "EQIX", "EQR", "EQT", "ERIE",
    "ES", "ESS", "ETN", "ETR", "EVRG", "EW", "EXC", "EXE", "EXPD", "EXPE",
    "EXR", "F", "FANG", "FAST", "FCX", "FDS", "FDX", "FE", "FFIV", "FICO",
    "FIS", "FISV", "FITB", "FIX", "FOX", "FOXA", "FRT", "FSLR", "FTNT", "FTV",
    "GD", "GDDY", "GE", "GEHC", "GEN", "GEV", "GILD", "GIS", "GL", "GLW",
    "GM", "GNRC", "GOOG", "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL",
    "HAS", "HBAN", "HCA", "HD", "HIG", "HII", "HLT", "HOLX", "HON", "HOOD",
    "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUBB", "HUM", "HWM", "IBKR",
    "IBM", "ICE", "IDXX", "IEX", "IFF", "INCY", "INTC", "INTU", "INVH", "IP",
    "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ", "J", "JBHT", "JBL",
    "JCI", "JKHY", "JNJ", "JPM", "KDP", "KEY", "KEYS", "KHC", "KIM", "KKR",
    "KLAC", "KMB", "KMI", "KO", "KR", "KVUE", "L", "LDOS", "LEN", "LH",
    "LHX", "LII", "LIN", "LITE", "LLY", "LMT", "LNT", "LOW", "LRCX", "LULU",
    "LUV", "LVS", "LYB", "LYV", "MA", "MAA", "MAR", "MAS", "MCD", "MCHP",
    "MCK", "MCO", "MDLZ", "MDT", "MET", "META", "MGM", "MKC", "MLM", "MMM",
    "MNST", "MO", "MOS", "MPC", "MPWR", "MRK", "MRNA", "MRSH", "MS", "MSCI",
    "MSFT", "MSI", "MTB", "MTD", "MU", "NCLH", "NDAQ", "NDSN", "NEE", "NEM",
    "NFLX", "NI", "NKE", "NOC", "NOW", "NRG", "NSC", "NTAP", "NTRS", "NUE",
    "NVDA", "NVR", "NWS", "NWSA", "NXPI", "O", "ODFL", "OKE", "OMC", "ON",
    "ORCL", "ORLY", "OTIS", "OXY", "PANW", "PAYX", "PCAR", "PCG", "PEG", "PEP",
    "PFE", "PFG", "PG", "PGR", "PH", "PHM", "PKG", "PLD", "PLTR", "PM",
    "PNC", "PNR", "PNW", "PODD", "POOL", "PPG", "PPL", "PRU", "PSA", "PSKY",
    "PSX", "PTC", "PWR", "PYPL", "Q", "QCOM", "RCL", "REG", "REGN", "RF",
    "RJF", "RL", "RMD", "ROK", "ROL", "ROP", "ROST", "RSG", "RTX", "RVTY",
    "SATS", "SBAC", "SBUX", "SCHW", "SHW", "SJM", "SLB", "SMCI", "SNA", "SNDK",
    "SNPS", "SO", "SOLV", "SPG", "SPGI", "SRE", "STE", "STLD", "STT", "STX",
    "STZ", "SW", "SWK", "SWKS", "SYF", "SYK", "SYY", "T", "TAP", "TDG",
    "TDY", "TECH", "TEL", "TER", "TFC", "TGT", "TJX", "TKO", "TMO", "TMUS",
    "TPL", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT",
    "TTD", "TTWO", "TXN", "TXT", "TYL", "UAL", "UBER", "UDR", "UHS", "ULTA",
    "UNH", "UNP", "UPS", "URI", "USB", "V", "VICI", "VLO", "VLTO", "VMC",
    "VRSK", "VRSN", "VRT", "VRTX", "VST", "VTR", "VTRS", "VZ", "WAB", "WAT",
    "WBD", "WDAY", "WDC", "WEC", "WELL", "WFC", "WM", "WMB", "WMT", "WRB",
    "WSM", "WST", "WTW", "WY", "WYNN", "XEL", "XOM", "XYL", "XYZ", "YUM",
    "ZBH", "ZBRA", "ZTS",
]

MIDCAP400_TICKERS = [
    "AA", "AAL", "AAON", "ACI", "ACM", "ADC", "AEIS", "AFG", "AGCO", "AHR",
    "AIT", "ALGM", "ALK", "ALLY", "ALV", "AM", "AMG", "AMH", "AMKR", "AN",
    "ANF", "APG", "APPF", "AR", "ARMK", "ARW", "ARWR", "ASB", "ASH", "ATI",
    "ATR", "AVAV", "AVNT", "AVT", "AVTR", "AXTA", "AYI", "BAH", "BBWI", "BC",
    "BCO", "BDC", "BHF", "BILL", "BIO", "BJ", "BKH", "BLD", "BLKB", "BMRN",
    "BRBR", "BRKR", "BROS", "BRX", "BSY", "BURL", "BWA", "BWXT", "BYD", "CACI",
    "CAR", "CART", "CASY", "CAVA", "CBSH", "CBT", "CCK", "CDP", "CELH", "CFR",
    "CG", "CGNX", "CHDN", "CHE", "CHH", "CHRD", "CHWY", "CLF", "CLH", "CMC",
    "CNH", "CNM", "CNO", "CNX", "CNXC", "COKE", "COLB", "COLM", "COTY", "CPRI",
    "CR", "CRBG", "CROX", "CRS", "CRUS", "CSL", "CTRE", "CUBE", "CUZ", "CVLT",
    "CW", "CXT", "CYTK", "DAR", "DBX", "DCI", "DINO", "DKS", "DLB", "DOCS",
    "DOCU", "DT", "DTM", "DUOL", "DY", "EEFT", "EGP", "EHC", "ELAN", "ELF",
    "ELS", "ENS", "ENSG", "ENTG", "EPR", "EQH", "ESAB", "ESNT", "EVR", "EWBC",
    "EXEL", "EXLS", "EXP", "EXPO", "FAF", "FBIN", "FCFS", "FCN", "FFIN", "FHI",
    "FHN", "FIVE", "FLEX", "FLG", "FLO", "FLR", "FLS", "FN", "FNB", "FND",
    "FNF", "FOUR", "FR", "FTI", "G", "GAP", "GATX", "GBCI", "GEF", "GGG",
    "GHC", "GLPI", "GME", "GMED", "GNTX", "GPK", "GT", "GTLS", "GWRE", "GXO",
    "H", "HAE", "HALO", "HGV", "HIMS", "HL", "HLI", "HLNE", "HOG", "HOMB",
    "HQY", "HR", "HRB", "HWC", "HXL", "IBOC", "IDA", "IDCC", "ILMN", "INGR",
    "IPGP", "IRT", "ITT", "JAZZ", "JEF", "JHG", "JLL", "KBH", "KBR", "KD",
    "KEX", "KNF", "KNSL", "KNX", "KRC", "KRG", "KTOS", "LAD", "LAMR", "LEA",
    "LECO", "LFUS", "LIVN", "LNTH", "LOPE", "LPX", "LSCC", "LSTR", "M", "MANH",
    "MASI", "MAT", "MEDP", "MIDD", "MKSI", "MLI", "MMS", "MOG.A", "MORN", "MP",
    "MSA", "MSM", "MTDR", "MTG", "MTN", "MTSI", "MTZ", "MUR", "MUSA", "MZTI",
    "NBIX", "NEU", "NFG", "NJR", "NLY", "NNN", "NOV", "NOVT", "NSA", "NTNX",
    "NVST", "NVT", "NWE", "NXST", "NXT", "NYT", "OC", "OGE", "OGS", "OHI",
    "OKTA", "OLED", "OLLI", "OLN", "ONB", "ONTO", "OPCH", "ORA", "ORI", "OSK",
    "OVV", "OZK", "PAG", "PATH", "PB", "PBF", "PCTY", "PEGA", "PEN", "PFGC",
    "PII", "PINS", "PK", "PLNT", "PNFP", "POR", "POST", "PPC", "PR", "PRI",
    "PSN", "PSTG", "PVH", "QLYS", "R", "RBA", "RBC", "REXR", "RGA", "RGEN",
    "RGLD", "RH", "RLI", "RMBS", "RNR", "ROIV", "RPM", "RRC", "RRX", "RS",
    "RYAN", "RYN", "SAIA", "SAIC", "SAM", "SARO", "SBRA", "SCI", "SEIC", "SF",
    "SFM", "SGI", "SHC", "SIGI", "SITM", "SLAB", "SLGN", "SLM", "SMG", "SNX",
    "SOLS", "SON", "SPXC", "SR", "SSB", "SSD", "ST", "STAG", "STRL", "STWD",
    "SWX", "SYNA", "TCBI", "TEX", "THC", "THG", "THO", "TKR", "TLN", "TMHC",
    "TNL", "TOL", "TREX", "TRU", "TTC", "TTEK", "TTMI", "TWLO", "TXNM", "TXRH",
    "UBSI", "UFPI", "UGI", "ULS", "UMBF", "UNM", "USFD", "UTHR", "VAL", "VC",
    "VFC", "VICR", "VLY", "VMI", "VNO", "VNOM", "VNT", "VOYA", "VVV", "WAL",
    "WBS", "WCC", "WEX", "WFRD", "WH", "WHR", "WING", "WLK", "WMG", "WMS",
    "WPC", "WSO", "WTFC", "WTRG", "WTS", "WWD", "XPO", "XRAY", "YETI", "ZION",
]

USA_SEGMENTS = {
    "USA_ALL": "Tüm USA (S&P 500 + MidCap 400)",
    "SP500": "S&P 500",
    "MIDCAP400": "S&P MidCap 400",
}

SCORING_WEIGHTS = {
    "financial_strength": 0.25,
    "growth": 0.20,
    "margin_quality": 0.15,
    "valuation": 0.20,
    "momentum": 0.20,
}

FINANCIAL_STRENGTH_WEIGHTS = {
    "roic": 0.40,
    "debt_to_equity": 0.25,
    "equity_to_assets": 0.20,
    "net_income_to_assets": 0.15,
}

GROWTH_WEIGHTS = {
    "revenue_growth": 0.25,
    "earnings_growth": 0.30,
    "revenue_cagr_3y": 0.20,
    "eps_cagr_3y": 0.25,
}

MARGIN_QUALITY_WEIGHTS = {
    "gross_margin": 0.20,
    "operating_margin": 0.30,
    "net_margin": 0.30,
    "margin_trend": 0.20,
}

VALUATION_WEIGHTS = {
    "pe": 0.20,
    "pb": 0.15,
    "ev_ebitda": 0.25,
    "peg": 0.40,
}

MOMENTUM_WEIGHTS = {
    "return_3m": 0.20,
    "return_6m": 0.25,
    "return_12m": 0.25,
    "distance_to_52w_high": 0.10,
    "relative_return_vs_index": 0.20,
}

REVERSE_SCORED_METRICS = {
    "debt_to_equity",
    "pe",
    "pb",
    "ev_ebitda",
    "peg",
}

RS_CATEGORIES = [
    (85, 100, "Elit"),
    (70, 85, "Güçlü"),
    (55, 70, "İzleme"),
    (40, 55, "Zayıf"),
    (0, 40, "Kaçın"),
]

WINSORIZE_LOWER = 0.05
WINSORIZE_UPPER = 0.95

SCORE_CATEGORIES = list(SCORING_WEIGHTS.keys())

DEFAULT_TOP_N = 10

API_REQUEST_TIMEOUT = 20
API_MAX_RETRIES = 1
API_RETRY_DELAY = 10

CACHE_TTL_MARKET_DATA = 300

LOG_LEVEL = os.getenv("SCREENER_LOG_LEVEL", "INFO")

REQUIRED_FIELDS_FOR_SCORING = [
    "equity", "net_income", "revenue", "total_assets",
]

FALLBACK_TO_MOCK = False

MIN_ROWS_FOR_SCORING = 3
