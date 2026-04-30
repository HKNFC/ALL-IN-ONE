# Mark Minervini Trading Platform - Web Application

Professional stock screening and signal generation platform based on Mark Minervini's SEPA methodology.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Run the Application

```bash
python3 app.py
```

### 3. Open in Browser

Navigate to: **http://localhost:5000**

---

## 📊 Features

- **Multi-Market Scanner**: BIST + US markets
- **Trend Template 2.0**: Automatic screening
- **VCP Detection**: Pattern recognition
- **Real-time Signals**: JSON API
- **Portfolio Management**: Risk tracking
- **Telegram Alerts**: Breakout notifications

---

## 🎯 API Endpoints

### Scanning

- `POST /api/scan/quick` - Quick scan (small list)
- `POST /api/scan/full` - Full scan (all stocks)

### Stock Details

- `GET /api/stock/<ticker>` - Get stock details

### Portfolio

- `GET /api/portfolio` - Get portfolio
- `POST /api/portfolio` - Add position

### Signals

- `GET /api/signals/history` - Signal history

### Stats

- `GET /api/stats` - Platform statistics

---

## 📁 Project Structure

```
MARK MİNERVİNİ/
├── app.py                    # Flask application
├── requirements.txt          # Dependencies
├── templates/
│   └── index.html           # Frontend HTML
├── static/
│   ├── css/
│   │   └── style.css        # Styles
│   └── js/
│       └── app.js           # JavaScript
├── sepa_scanner.py          # SEPA scanner
├── universal_scanner.py     # Universal scanner
└── [other scanners]
```

---

## 🔧 Configuration

### Telegram Integration

Edit `telegram_config.json`:

```json
{
  "telegram_bot_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID"
}
```

### SEPA Config

Edit `sepa_config.json`:

```json
{
  "hard_stop_pct": 7.0,
  "profit_target_pct": 15.0,
  "volume_spike_threshold": 1.5
}
```

---

## 🌐 Deployment

### Local Deployment

```bash
python3 app.py
```

### Production Deployment (Gunicorn)

```bash
pip3 install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Docker Deployment

```bash
docker build -t minervini-platform .
docker run -p 5000:5000 minervini-platform
```

---

## 📱 Mobile Responsive

The platform is fully responsive and works on:
- Desktop (1920x1080+)
- Tablet (768x1024)
- Mobile (375x667+)

---

## ⚠️ Important Notes

### Risk Disclaimer

This platform is for educational and analysis purposes only. It does not constitute investment advice. Always:
- Do your own research
- Use proper risk management
- Never invest more than you can afford to lose

### Data Source

- Stock data: Yahoo Finance API (free tier)
- Rate limits apply
- Some stocks may not be available

### System Requirements

- Python 3.9+
- 2GB RAM minimum
- Internet connection
- Modern web browser

---

## 🔒 Security

### Best Practices

1. **Never commit secrets** to git
2. Use environment variables for sensitive data
3. Enable HTTPS in production
4. Use strong passwords
5. Regular backups

### .gitignore

```
telegram_config.json
sepa_config.json
my_portfolio.csv
*.pyc
__pycache__/
```

---

## 📈 Performance

### Optimization Tips

1. **Caching**: Implement Redis for API responses
2. **Database**: Use PostgreSQL for large datasets
3. **CDN**: Serve static files from CDN
4. **Workers**: Use Celery for background tasks

### Monitoring

- Use logging for debugging
- Monitor API response times
- Track error rates
- Set up alerts

---

## 🆘 Troubleshooting

### Port Already in Use

```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9
```

### Module Not Found

```bash
pip3 install -r requirements.txt --upgrade
```

### CORS Errors

Already configured with `flask-cors`

### Data Issues

- Check internet connection
- Verify ticker symbols
- Yahoo Finance may have delays

---

## 📚 Resources

### Mark Minervini Books

1. Trade Like a Stock Market Wizard
2. Think & Trade Like a Champion
3. Momentum Masters

### Online Resources

- [Minervini Private Access](https://www.minervini.com)
- [@markminervini](https://twitter.com/markminervini)

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## 📄 License

MIT License - See LICENSE file

---

## 👨‍💻 Author

Mark Minervini Trading Platform
Built with Flask, Python, and ❤️

---

## 🎉 Acknowledgments

- Mark Minervini for the SEPA methodology
- Yahoo Finance for market data
- Flask and Python communities

---

**Happy Trading! 📈**
