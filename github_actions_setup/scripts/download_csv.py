#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google DriveのSCOREフォルダからCSVをダウンロードするスクリプト
"""
import os, json, sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import io

def main():
    # 環境変数から認証情報を取得
    creds_json = os.environ.get('GDRIVE_CREDENTIALS', '')
    folder_id = os.environ.get('GDRIVE_FOLDER_ID', '')

    if not creds_json or not folder_id:
        print("[ERROR] GDRIVE_CREDENTIALS or GDRIVE_FOLDER_ID not set")
        sys.exit(1)

    # 認証
    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    service = build('drive', 'v3', credentials=creds)

    # 出力フォルダ作成
    os.makedirs('score_data', exist_ok=True)

    # SCOREフォルダ内のCSVを一覧取得
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='text/csv' and trashed=false",
        fields="files(id, name)",
        pageSize=100
    ).execute()

    files = results.get('files', [])
    if not files:
        print("[WARN] No CSV files found in the folder")
        return

    print(f"Found {len(files)} CSV files")

    # 各CSVをダウンロード
    for file in files:
        file_id = file['id']
        file_name = file['name']
        output_path = os.path.join('score_data', file_name)

        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        with open(output_path, 'wb') as f:
            f.write(fh.getvalue())
        print(f"  Downloaded: {file_name}")

    print("Done!")

if __name__ == '__main__':
    main()
