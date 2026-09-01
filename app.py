"""Launch the local review UI.

    python app.py

Opens http://127.0.0.1:5000/ in your browser: review the games found on Drive,
tick the ones to publish, then upload. Nothing is sent to Sanity until you click.
"""
from web.app import main

if __name__ == "__main__":
    main()
