from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
import os
import pdb
from base64 import b64decode
from clint.textui import progress

from logger import logger

# If modifying these scopes, delete the file token.pickle.
G_DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]
GSUITE_USER_EMAIL = 'it@miamiadschool.com'
G_DRIVE_FOLDER_ID = '1dcI6AN_IidAT20BXXQYBv1Oxih0DKQFw'
G_DRIVE_FOLDER = 'https://drive.google.com/drive/folders/0AK09kp6LWV7OUk9PVA'
G_DRIVE_MANAGER_EMAILS = [
    'pippa@miamiadschool.com',
    'julie@miamiadschool.com',
    'manolo@miamiadschool.com',
    'stephanie@miamiadschool.com',
    'z@miamiadschool.com',
    'zoom-recordings-to-drive@zoom-recordings-to-drive.iam.gserviceaccount.com'
]
G_DRIVE_CONTRIBUTER_EMAILS = [
    'pippa@miamiadschool.com',
    'julie@miamiadschool.com',
    'manolo@miamiadschool.com',
    'stephanie@miamiadschool.com',
    'z@miamiadschool.com',
    'zoom-recordings-to-drive@zoom-recordings-to-drive.iam.gserviceaccount.com'
]
G_DRIVE_VIEWER_EMAILS = [
    'pippa@miamiadschool.com',
    'julie@miamiadschool.com',
    'manolo@miamiadschool.com',
    'stephanie@miamiadschool.com',
    'z@miamiadschool.com',
    'zoom-recordings-to-drive@zoom-recordings-to-drive.iam.gserviceaccount.com'
]

# folders
ADMIN_FOLDER = 'Administration'
STUDENT_WORK_FOLDER = 'Student Work'
RECORDINGS_FOLDER = 'Recordings'

# roles
MANAGER_ROLE = 'writer'
CONTRIBUTOR_ROLE = 'commenter'
VIEWER_ROLE = 'reader'

# columns
COURSE_LINK = 'Google Drive: Course Link'
ADMIN_LINK = 'Google Drive: Admin'
STUDENT_WORK_LINK = 'Google Drive: Student Work'
RECORDINGS_LINK = 'Google Drive: Recordings'

UPLOAD_CHUNKSIZE = 1024

class GDrive:
    students = []
    folders = []

    def __init__(self):
        # OAuth2 using service key
        self.credentials = service_account.Credentials.from_service_account_file(
            './creds/google_secret.json',
            scopes=G_DRIVE_SCOPES,
            subject=GSUITE_USER_EMAIL)

        self.drive_service = build('drive', 'v3', credentials=self.credentials, cache_discovery=False)

    def setup(self, spread):
        self.ccs = spread.ccs # CampusCafe Course Schedule Sheet
        self.sr = spread.sr # Student Roster
        # self.fc = fc # Faculty CRM
        # self.cs = cs # Calendar Schedule

    def read_students_for_course(self, unique_id):
        students = ['liorwn@gmail.com']
        for course, addr in zip(self.sr['COURSE'], self.sr['ADDRESS']):
            if unique_id in course:
                students.append(addr)
        return students

    def check_folder(self, folder_name, parent_id):
        query = f"'{parent_id}' in parents"
        page_token = None
        folder_id = None
        while True:
            response = self.drive_service.files().list(q=query,
                      spaces='drive',
                      fields='nextPageToken, files(id, name)',
                      pageToken=page_token).execute()
            for file in response.get('files', []):
                # Process change
                if file.get('name') == folder_name:
                    folder_id = file.get('id')
                    break
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break

        if not folder_id:
            file_metadata = {
                'name': folder_name,
                "parents": [parent_id],
                'mimeType': 'application/vnd.google-apps.folder'
            }
            file = self.drive_service.files().create(body=file_metadata,
                                    fields='id').execute()
            folder_id = file.get('id')

        return folder_id

    def clear_old_recordings(self, meeting, recordings):
        logger.info(f'--- clear old recordings for meeting {meeting["uuid"]} as not all of them uploaded correctly ')
        try:
            for rec in recordings:
                self.drive_service.files().delete(fileId=rec['file_id']).execute()
        except Exception as E:
            logger.warning(str(E))

    def upload_file(self, temporary_file_name, filename, file_type, vid, parent_id):
        total_size = int(vid.headers.get('content-length'))
        file_id = None
        mimetype = ""
        if file_type == 'MP4':
            mimetype = "video/mp4"
            filename = f'{filename}.mp4'
        elif file_type == 'M4A':
            mimetype = "audio/m4a"
            filename = f'{filename}.m4a'
        elif file_type == 'CHAT':
            mimetype = 'text/plain'
            filename = f'{filename}.txt'
        elif file_type == 'TRANSCRIPT':
            filename = f'{filename}.vtt'
            mimetype = 'text/vtt'

        with open(temporary_file_name, 'rb') as temporary_file:
            chunk_size = 1024*1024
            # file_bytes = BytesIO(vid.content)
            media = MediaIoBaseUpload(temporary_file, mimetype, resumable=True, chunksize=chunk_size)
            body = { "name": filename, "parents": [parent_id], "mimetype": mimetype }
            res = self.drive_service.files().create(body=body, media_body=media, fields='id').execute()
            os.remove(temp_filename)
            file_id = res.get('id')

            logger.info(f'**** uploaded file {filename} in drive folder_id {parent_id}')
            
        return file_id
       
    def create_drive_folder(self, name, parent_id, supportsAllDrives=True):
        try:
            file_metadata = {
                'name': name,
                'parents': [parent_id],
                'writersCanShare': True,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            file = self.drive_service.files().create(
                body=file_metadata, 
                fields='id',
                supportsAllDrives=supportsAllDrives
            ).execute()
            return file.get('id')
        except Exception as E:
            logger.warning(str(E))

    def callback(self, request_id, response, exception):
        if exception:
            # Handle error
            logger.warning(str(exception))
        else:
            pass

    def share_drive_folder(self, file_id, emails, role):
        try:
            batch = self.drive_service.new_batch_http_request(callback=self.callback)
            for email in emails:
                user_permission = {
                    'type': 'user',
                    'role': role,
                    'emailAddress': email
                }
                batch.add(self.drive_service.permissions().create(
                    fileId=file_id,
                    body=user_permission,
                    supportsAllDrives=True,
                    fields='id',
                ))
            batch.execute()
        except Exception as E:
            logger.warning(str(E))     

    def share_drive_folder_without_batch(self, file_id, emails, role):
        try:
            for email in emails:
                user_permission = {
                    'type': 'user',
                    'role': role,
                    'emailAddress': email
                }
                self.drive_service.permissions().create(
                    fileId=file_id,
                    body=user_permission,
                    supportsAllDrives=True,
                    fields='id',
                )
        except Exception as E:
            logger.warning(str(E))

    def create_share_folder(self, name, parent_id, emails, role):
        file_id = self.create_drive_folder(name, parent_id)
        if role == 'commenter':
            self.share_drive_folder_without_batch(file_id, emails, role)
        else:
            self.share_drive_folder(file_id, emails, role)

        return file_id

    def update_ccs_data(self, index, folder):
        parent_link = f"https://drive.google.com/drive/folders/{folder['parent_id']}"
        admin_link = f"https://drive.google.com/drive/folders/{folder['admin_id']}"
        contr_link = f"https://drive.google.com/drive/folders/{folder['contr_id']}"
        viewer_link = f"https://drive.google.com/drive/folders/{folder['viewer_id']}"
        self.ccs.at[index, COURSE_LINK] = parent_link
        self.ccs.at[index, ADMIN_LINK] = admin_link
        self.ccs.at[index, STUDENT_WORK_LINK] = contr_link
        self.ccs.at[index, RECORDINGS_LINK] = viewer_link

    def create_drive_folders(self, name, index, unique_id):
        # Create parent folder and then update df with link
        parent_id = self.create_drive_folder(name, G_DRIVE_FOLDER_ID)

        # Create Administration folder and then share manager permission and then update df with link
        admin_id = self.create_share_folder(ADMIN_FOLDER, parent_id, G_DRIVE_MANAGER_EMAILS, MANAGER_ROLE)

        students = self.read_students_for_course(unique_id)
        # Create Student Work folder and then share contributor permission and then update df with link
        contr_id = self.create_share_folder(STUDENT_WORK_FOLDER, parent_id, students, CONTRIBUTOR_ROLE)
       
        # Create Recordings folder and then share viewer permission and then update df with link
        viewer_id = self.create_share_folder(RECORDINGS_FOLDER, parent_id, G_DRIVE_VIEWER_EMAILS, VIEWER_ROLE)

        folder = {
            'name': name,
            'parent_id': parent_id,
            'admin_id': admin_id,
            'contr_id': contr_id,
            'viewer_id': viewer_id
        }
        self.folders.append(folder)
        return folder

    def is_new_folder(self, name):
        myfolder = None
        for folder in self.folders:
            if folder['name'] == name:
                myfolder = folder
                break
        return myfolder

    def generate_links_and_share_permission(self):
        '''
            Read names from CampusCafe Course Schedule Sheet
            @name: Course Number (Column C) + ": " + Description (Column H)
        '''
        index = 0
        for cn, desc, unique_id in zip(self.ccs['Course Number'], self.ccs['Description'], self.ccs['Unique ID']):
            name = f"{cn}: {desc}"
            myfolder = self.is_new_folder(name)
            if not myfolder:
                myfolder = self.create_drive_folders(name, index, unique_id)
            self.update_ccs_data(index, myfolder)

            index += 1
            # break

        return self.ccs

if __name__ == '__main__':
    g_drive = GDrive()
