"""Optional paired LAN access for the mobile prototype."""
from http.cookies import SimpleCookie
import ipaddress
import secrets
import socket
import threading
import time

def private_addresses():
    found = set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            a = ipaddress.ip_address(result[4][0])
            if a.is_private and not a.is_loopback and not a.is_link_local:
                found.add(str(a))
    except OSError:
        pass
    return sorted(found)

class MobileAccess:
    def __init__(self, port, lan=False, addresses=None):
        self.port, self.lan = port, lan
        self.addresses = addresses if addresses is not None else private_addresses() if lan else []
        self.code = f"{secrets.randbelow(1_000_000):06d}"
        self.cookie_token = secrets.token_urlsafe(32)
        self.attempts = {}
        self.lock = threading.Lock()

    def check_origin(self, host, origin):
        allowed = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        allowed.update(f"{a}:{self.port}" for a in self.addresses)
        if host not in allowed:
            raise ValueError("访问地址未启用，请使用服务显示的本机或局域网地址。")
        if origin and origin != "http://" + host:
            raise ValueError("不接受跨站请求。")

    def is_local(self, address):
        return ipaddress.ip_address(address).is_loopback

    def authorized(self, address, cookie):
        if self.is_local(address):
            return True
        if not self.lan or not ipaddress.ip_address(address).is_private:
            return False
        try:
            token = SimpleCookie(cookie or "").get("inspector_pair")
            return token is not None and secrets.compare_digest(token.value, self.cookie_token)
        except Exception:
            return False

    def pair(self, address, code):
        if not self.lan or not ipaddress.ip_address(address).is_private:
            raise ValueError("当前未启用局域网手机访问。")
        with self.lock:
            count, started = self.attempts.get(address, (0, time.monotonic()))
            if time.monotonic() - started > 60:
                count, started = 0, time.monotonic()
            if count >= 5:
                raise ValueError("连接码尝试次数过多，请一分钟后再试。")
            self.attempts[address] = (count + 1, started)
            if not secrets.compare_digest(str(code), self.code):
                raise ValueError("连接码不正确，请查看电脑页面“我的 → 手机访问”。")
            self.attempts.pop(address, None)
        return f"inspector_pair={self.cookie_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200"

    def info(self, local):
        result = {"is_local": local, "lan_enabled": self.lan}
        if local:
            result.update(urls=[f"http://{a}:{self.port}/" for a in self.addresses], pair_code=self.code if self.lan else None)
        return result
