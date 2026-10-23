"""App-scoped Windows Credential Manager storage. No plaintext file fallback."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json,os

TARGET = "Jianjing.HotelInspector.Vision.v1"
TEST_PREFIX = TARGET + ".test."
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_BLOB_BYTES = 5 * 512

class CredentialError(ValueError):
    pass

class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags",wintypes.DWORD),("Type",wintypes.DWORD),
        ("TargetName",wintypes.LPWSTR),("Comment",wintypes.LPWSTR),
        ("LastWritten",wintypes.FILETIME),("CredentialBlobSize",wintypes.DWORD),
        ("CredentialBlob",ctypes.POINTER(wintypes.BYTE)),("Persist",wintypes.DWORD),
        ("AttributeCount",wintypes.DWORD),("Attributes",ctypes.c_void_p),
        ("TargetAlias",wintypes.LPWSTR),("UserName",wintypes.LPWSTR),
    ]
PCREDENTIALW = ctypes.POINTER(CREDENTIALW)

class CredentialStore:
    def __init__(self,target=None,enabled=None):
        self.target=target or os.environ.get("INSPECTOR_CREDENTIAL_TARGET",TARGET)
        if self.target != TARGET and not self.target.startswith(TEST_PREFIX):
            raise CredentialError("Credential target must belong to this application.")
        self.supported=os.name=="nt" and (enabled if enabled is not None else os.environ.get("INSPECTOR_DISABLE_CREDENTIAL_STORE")!="1")
        self._dll=None

    def _api(self):
        if not self.supported:
            raise CredentialError("Windows credential storage is unavailable; use session-only configuration.")
        if self._dll is None:
            dll=ctypes.WinDLL("Advapi32.dll",use_last_error=True)
            dll.CredWriteW.argtypes=[PCREDENTIALW,wintypes.DWORD];dll.CredWriteW.restype=wintypes.BOOL
            dll.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(PCREDENTIALW)];dll.CredReadW.restype=wintypes.BOOL
            dll.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD];dll.CredDeleteW.restype=wintypes.BOOL
            dll.CredFree.argtypes=[ctypes.c_void_p];dll.CredFree.restype=None
            self._dll=dll
        return self._dll

    def load(self):
        if not self.supported:return None
        api=self._api();ptr=PCREDENTIALW()
        if not api.CredReadW(self.target,CRED_TYPE_GENERIC,0,ctypes.byref(ptr)):
            if ctypes.get_last_error()==ERROR_NOT_FOUND:return None
            raise CredentialError("Windows could not read this application's saved model configuration.")
        try:
            value=ptr.contents
            if not 0 < value.CredentialBlobSize <= MAX_BLOB_BYTES:raise CredentialError("Saved model configuration is invalid.")
            try:
                data=json.loads(ctypes.string_at(value.CredentialBlob,value.CredentialBlobSize).decode("utf-8"))
            except (ValueError,UnicodeError):raise CredentialError("Saved model configuration is invalid.") from None
            if not isinstance(data,dict) or data.get("schema")!=1 or any(not isinstance(data.get(k),str) or not data[k].strip() for k in ("api_key","base_url","model")):
                raise CredentialError("Saved model configuration is invalid.")
            return {k:data[k] for k in ("api_key","base_url","model")}
        finally:api.CredFree(ptr)

    def save(self,config):
        api=self._api()
        if any(not isinstance(config.get(k),str) or not config[k].strip() for k in ("api_key","base_url","model")):
            raise CredentialError("Model configuration is incomplete.")
        blob=json.dumps({"schema":1,**{k:config[k] for k in ("api_key","base_url","model")}},ensure_ascii=False,separators=(",",":")).encode("utf-8")
        if len(blob)>MAX_BLOB_BYTES:raise CredentialError("Model configuration exceeds Windows credential storage capacity.")
        buffer=ctypes.create_string_buffer(blob)
        value=CREDENTIALW()
        value.Flags=0;value.Type=CRED_TYPE_GENERIC;value.TargetName=self.target
        value.Comment="Jianjing local vision-model configuration"
        value.CredentialBlobSize=len(blob);value.CredentialBlob=ctypes.cast(buffer,ctypes.POINTER(wintypes.BYTE))
        value.Persist=CRED_PERSIST_LOCAL_MACHINE;value.AttributeCount=0;value.UserName="Jianjing"
        try:
            if not api.CredWriteW(ctypes.byref(value),0):
                raise CredentialError("Windows could not save the configuration. The current connection was not changed.")
        finally:ctypes.memset(buffer,0,len(buffer))

    def delete(self):
        if not self.supported:return
        api=self._api()
        if not api.CredDeleteW(self.target,CRED_TYPE_GENERIC,0) and ctypes.get_last_error()!=ERROR_NOT_FOUND:
            raise CredentialError("Windows could not remove this application's saved configuration.")
