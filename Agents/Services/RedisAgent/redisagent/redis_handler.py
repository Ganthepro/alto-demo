import json
import redis


class RedisHandler:
    def __init__(self, host, port, password, database=0):
        """Redis handler class
        :param host: Redis host address (default: localhost)
        :param port: Redis port (default: 6379)
        :param password: Redis password (default: None)
        :param database: Redis database (default: 0)
        """
        self.host = host
        self.port = port
        self.password = password
        self.database = database
        self.redis = redis.Redis(host=self.host, port=self.port, password=self.password, db=self.database)

    def _update_datatype(self, data: str):
        results = dict()
        for key in data.keys():
            _new_key = key.decode("utf-8")
            results[_new_key] = data.get(key)
        return results

    def set(self, key, value):
        self.redis.set(key, value)

    def hset(self, hash_field, key, value):
        self.redis.hset(hash_field, key, value)

    def get(self, key):
        return self.redis.get(key)
    
    def hget(self, hash_field, key):
        return self.redis.hget(hash_field, key)
    
    def hget_key(self, hash_field):
        return self.redis.hkeys(hash_field)

    def hget_val(self, hash_field):
        return self.redis.hvals(hash_field)

    def hget_all(self, hash_field):
        _hash_data = self.redis.hgetall(hash_field)
        return self._update_datatype(_hash_data)

    def list_key(self):
        return self.redis.keys()

    def list_key_start_with(self, key):
        return self.redis.keys(key + '*')

    def exists(self, key):
        return self.redis.exists(key)

    def delete(self, key):
        self.redis.delete(key)

    # def flush(self):
    #     """Flush all data in Redis database (delete all keys)"""
    #     self.redis.flushdb()


if __name__ == '__main__':
    # create Redis handler object
    redis_handler = RedisHandler(
        host='localhost',  # 10.10.10.152
        port=6379,
        password='NjzZ2EKz6cYZAN3xFaCV4d4h9xB28Y6N',
        database=0
    )

    # get all keys
    keys = redis_handler.list_key()
    keys = sorted(keys)
    print(len(keys), keys)
    print()

    data: dict = redis_handler.hget_all('')
    for key in data.keys():
        _data: str = data[key]
        print(key, json.loads(_data))
        print()

    # delete all keys
    # for key in keys:
    #     redis_handler.delete(key)
    # keys = redis_handler.list_key()
    # print(keys)
