import socket


IP = "192.168.1.128";
PORT = 80;

def http_get(content):
    global IP, PORT;
    c = socket.socket();
    ip = IP;
    c.connect((ip, PORT));
    print("content", content);
    c.sendall(content);
    return c.recv(2048);

host = "192.168.1.117"

body = '{"client_set": [{"ip":"192.168.1.117","port":9533,"protocol":"UDP"},{"protocol":"","ip":""},{"protocol":"","ip":""},{"protocol":"","ip":""}]}'
c_len = len(body);

content = "POST /config?command=client" + \
            f" HTTP/1.1\r\nUser-Agent: LuaSocket 2.0.2\r\nContent-Type: application/json\r\n" + \
            f"Content-Length: {c_len}\r\n" + \
            f"Host: {host}\r\n\r\n" + \
            body;

res = http_get(content.encode("utf-8"));
print(res)
