import os
from pathlib import Path

# .env dosyasını yükle (python-dotenv varsa)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass

TWELVEDATA_API_KEY = os.environ.get('TWELVEDATA_API_KEY', '')

if not TWELVEDATA_API_KEY:
    raise RuntimeError(
        "TWELVEDATA_API_KEY bulunamadı!\n"
        "Lütfen proje klasörüne .env dosyası oluşturun:\n"
        "  TWELVEDATA_API_KEY=your_api_key_here"
    )
