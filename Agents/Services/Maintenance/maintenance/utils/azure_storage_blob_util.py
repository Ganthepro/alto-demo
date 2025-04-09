import os
from azure.storage.blob import ContainerClient

class BlobClient:
    def __init__(self, connection_string: str, container_name: str):
        self.connection_str = connection_string
        self.container_name = container_name
        self.container_client = ContainerClient.from_connection_string(conn_str=self.connection_str,
                                                                       container_name=self.container_name)

    def get_all_blobs(self):
        """
        return list of all blob names
        """
        blob_list = self.container_client.list_blobs()
        name_list = [blob['name'] for blob in blob_list]
        return name_list

    def upload(self, source, dest, content_type=None):
        """
        Upload a file or directory to a path inside the container
        """
        if (os.path.isdir(source)):
            self.upload_dir(source, dest)
        else:
            self.upload_file(source, dest, content_type)

    def upload_file(self, source, dest, content_type=None):
        """
        Upload a single file to a path inside the container
        """
        print(f'Uploading {source} to {dest}')
        with open(source, 'rb') as data:
            self.container_client.upload_blob(name=dest, data=data, content_type=content_type)

    def upload_dir(self, source, dest):
        """
        Upload a directory to a path inside the container
        """
        prefix = '' if dest == '' else dest + '/'
        prefix += os.path.basename(source) + '/'
        for root, dirs, files in os.walk(source):
            for name in files:
                dir_part = os.path.relpath(root, source)
                dir_part = '' if dir_part == '.' else dir_part + '/'
                file_path = os.path.join(root, name)
                blob_path = prefix + dir_part + name
                self.upload_file(file_path, blob_path)

    def upload_encoded_image(self, path, img):
        """
        Upload numpy-array image to a path inside the container
        """
        encoded_img = cv2.imencode(".jpg", img)[1].tobytes()
        self.container_client.upload_blob(name=path, data=encoded_img)

    def download(self, source, dest):
        """
        Download a file or directory to a path on the local filesystem
        """
        if not dest:
            raise Exception('A destination must be provided')

        blobs = self.ls_files(source, recursive=True)
        if blobs:
            # if source is a directory, dest must also be a directory
            if not source == '' and not source.endswith('/'):
                source += '/'
            if not dest.endswith('/'):
                dest += '/'
            # append the directory name from source to the destination
            dest += os.path.basename(os.path.normpath(source)) + '/'

            blobs = [source + blob for blob in blobs]
            for blob in blobs:
                blob_dest = dest + os.path.relpath(blob, source)
                self.download_file(blob, blob_dest)
        else:
            self.download_file(source, dest)

    def download_file(self, source: str, dest: str):
        """
        Download a single file to a path on the local filesystem
        """
        # dest is a dir

        # dest is a directory if ending with '/' or '.', otherwise it's a file
        if dest.endswith("."):
            dest += "/"
        blob_dest = dest + os.path.basename(source) if dest.endswith("/") else dest

        print(f'Downloading {source} to {blob_dest}')
        os.makedirs(os.path.dirname(blob_dest), exist_ok=True)
        bc = self.container_client.get_blob_client(blob=source)
        with open(blob_dest, 'wb') as file:
            data = bc.download_blob()
            file.write(data.readall())

    def ls_files(self, path: str, recursive: bool = False):
        """
        List files under a path, optionally recursively
        """
        if not path == '' and not path.endswith('/'):
            path += '/'

        blob_tier = self.container_client.list_blobs(name_starts_with=path)
        files = []
        for blob in blob_tier:
            relative_path = os.path.relpath(blob.name, path)
            if recursive or not '/' in relative_path:
                files.append(relative_path)

        return files

    def ls_dirs(self, path, recursive=False):
        """
        List directories under a path, optionally recursively
        """
        if not path == '' and not path.endswith('/'):
            path += '/'

        blob_iter = self.container_client.list_blobs(name_starts_with=path)
        dirs = []
        for blob in blob_iter:
            relative_dir = os.path.dirname(os.path.relpath(blob.name, path))
            if relative_dir and (recursive or not '/' in relative_dir) and not relative_dir in dirs:
                dirs.append(relative_dir)

        return dirs

    def delete_dir(self, path):
        """
        Delete dir or file
        """
        if not path == '' and not path.endswith('/'):
            path += '/'

        file_paths = [f'{path}{file}' for file in self.ls_files(path, recursive=True)]
        for file_path in file_paths:
            print('deleting: ', file_path)
            self.container_client.delete_blob(blob=file_path)
