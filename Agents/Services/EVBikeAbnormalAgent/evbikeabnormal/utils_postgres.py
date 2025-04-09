import psycopg2
from psycopg2 import Error


class PostgresManage:
    def __init__(self):
        self.user = "altotech@altopostgres"
        self.password = "Magicalmint636"
        self.host = "altopostgres.postgres.database.azure.com"
        self.port = "5432"
        self.database = "postgres"
        self.connection = self.initiate_connection()


    def initiate_connection(self):
        try:
            print("Connecting to PostgresSQL ...")
            connection = psycopg2.connect(user=self.user,
                                      password=self.password,
                                      host=self.host,
                                      port=self.port,
                                      database=self.database)
            print("Successfully connected to PostgresSQL")
            return connection

        except (Exception, Error) as error:
            print("Error while connecting to PostgreSQL", error)
            return None


    def execute_query(self, query):
        """execute the input query"""
        if self.connection is not None:
            cursor = self.connection.cursor()
            cursor.execute(query)
            records = cursor.fetchall()
            records_dict = self.make_dict_record(cursor, records)
            return records_dict
        else:
            return None


    def make_dict_record(self, cursor, records):
        """create a dict format from the input query records"""
        try:
            column_names = [description.name for description in list(cursor.description)]

            records_dict = []
            for record in records:
                row_dict = {}
                for i, col in enumerate(column_names):
                    row_dict[col] = record[i]
                records_dict.append(row_dict)

            return records_dict

        except (Exception, Error) as error:
            print("Error while connecting to PostgreSQL", error)
            return None


# class demo
if __name__ == "__main__":
    psql = PostgresManage()
    query = '''SELECT * FROM ev_rider;'''
    records = psql.execute_query(query)
    for record in records:
        print(record)
