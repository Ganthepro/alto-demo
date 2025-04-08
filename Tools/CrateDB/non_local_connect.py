import time
from crate import client


if __name__ == '__main__':
    query = f"""SELECT device_id FROM altodemo WHERE timestamp>=1652635378;"""

    connection = client.connect('http://10.10.30.162:4200/', username="alto_user", password="88888888")
    cursor = connection.cursor()
    cursor.execute(query)
    print(cursor.fetchall())


