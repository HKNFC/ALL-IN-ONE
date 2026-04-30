# ALL-IN-ONE Yatırım Platformu

## Modüller ve Portlar
| Modül | Port |
|-------|------|
| GEMINI-PIYASA-ZAMANLAMA-MODULU | 8501 |
| MARK MİNERVİNİ | 5555 |
| Portfolio-Optimizer | 8505 |
| SUPER-INVESTOR-CHATGPT | 8503 |
| Ensemble-Portfoy | 8506 |
| piyasa-dashboard | 8501 |
| ALL-IN-ONE-PLATFORM (portal) | 5600 |

## Yeni Mac'te Kurulum
```bash
git clone https://github.com/HKNFC/ALL-IN-ONE.git
cd ALL-IN-ONE
pip install -r requirements.txt
```

## API Anahtarları
Her modülün klasöründe `.env` dosyası oluştur:
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
TWELVEDATA_API_KEY=...
```

## Başlatma
ALL-IN-ONE-PLATFORM/start_all.sh ile tüm modüller başlatılır.
