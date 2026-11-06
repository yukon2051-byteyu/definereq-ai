# Hugging Face Spaces（Docker 方式）用の実行環境
# 秘密情報はここに書かず、Space の Settings > Secrets に登録する（実行時に環境変数として渡される）
FROM python:3.12-slim

# Spaces はユーザー番号 1000 で動かすため、同じ番号の利用者を作る
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1
WORKDIR /home/user/app

# ライブラリを先に入れる（コードだけ変えたときは、この段を作り直さずに済む）
# 動画処理の PyAV は ffmpeg を内蔵しているため、OS の追加導入は不要
# 日本語はブラウザ側のフォント（Google Fonts、読めなければ端末の標準フォント）で表示する
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# 動画は Git LFS 管理のため、参照ファイルだけが届いた場合は実体を取得する
RUN python -m definereq.demos.fetch_media

# README の app_port（8501）と合わせる
# Spaces は中継サーバーを通して表示するため、アップロードが拒否されないよう XSRF と CORS の確認を外す
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", \
     "--server.enableXsrfProtection=false", "--server.enableCORS=false"]
