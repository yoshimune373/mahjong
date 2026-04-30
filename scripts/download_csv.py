#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, sys
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

    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='text/csv' and trashed=false",
        fields="files(id, name)",
        pageSize=100
    ).execute()

    files = results.get('files', [])
    if not files:
        print("[WARN] No CSV files found in th
