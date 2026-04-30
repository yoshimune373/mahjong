#!/usr/bin/env python3
import os, json, sys, glob
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import io

def main():
    creds_json = os.environ.get('GDRIVE_CREDENTIALS', '')
    folder_id = os.environ.get('GDRIVE_FOLDER_ID', '')

    if not creds_json or not folder_id:
        print("[ERROR] GDRIVE_CREDENTIALS or GDRIVE_FOLDER_ID not set")
        sys.exit(1)

    creds_dict = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    service = build('drive', 'v3', credentials=creds)

    os.makedirs('score_data', exist_ok=True)

    # mimeTypeを限定しないで全ファイルを取得してみる
    results = service.files().list(
        q="'" + folder_id + "' in parents and trashed=false",
        fields="files(id, name, mimeType)",
        pageSize=100
    ).execute()

    files = results.get('files', [])
    print("Total files in folder: " + str(len(files)))
    for f in files:
        print("  - " + f['name'] + " (" + f['mimeType'] + ")")

    csv_files = [f for f in files if 'csv' in f['mimeType'] or f['name'].endswith('.csv')]
    print("CSV files: " + str(len(csv_files)))

    for file in csv_files:
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
        print("Downloaded: " + file_name)

    # ダウンロード後の確認
    downloaded = glob.glob('score_data/*.csv')
    print("Files in score_data: " + str(len(downloaded)))
    for f in downloaded:
        print("  - " + f)

    print("Done!")

if __name__ == '__main__':
    main()
