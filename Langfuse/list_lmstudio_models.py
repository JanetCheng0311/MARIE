#!/usr/bin/env python3
"""
Probe a local LMStudio / model-serving API for available models.
Usage:
  python list_lmstudio_models.py [host]
If host omitted, reads from env `SERVER_API_HOST` or `SERVER_IP` or uses localhost:1234.

This script tries several common endpoints and also attempts to use the `lmstudio` Python
client if it's installed.
"""
import os
import sys
import requests
import json
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

def get_base_host(h):
    if not h:
        return None
    h = h.strip()
    # If it's a full URL, extract the scheme and netloc only
    if "://" in h:
        parsed = urlparse(h)
        return f"{parsed.scheme}://{parsed.netloc}"
    # If no scheme, assume http
    return f"http://{h}"

DEFAULT_HOSTS = [
    os.environ.get("SERVER_API_HOST"),
    os.environ.get("SERVER_IP"),
    os.environ.get("SERVER"),
    "127.0.0.1:1234",
]

TRIED = []


def normalize_host(h):
    if not h:
        return None
    h = str(h).strip()
    if h.startswith("http://") or h.startswith("https://"):
        return h.rstrip("/")
    return f"http://{h.rstrip('/')}"


def try_endpoints(base_url):
    endpoints = [
        "/v1/models",
        "/models",
        "/api/models",
        "/api/v1/models",
        "/v1/engines",
        "/engines",
        "/api/v1/engines",
        "/api/v0/models",
    ]
    results = {}
    for ep in endpoints:
        url = base_url + ep
        try:
            r = requests.get(url, timeout=5)
            results[ep] = {
                "status": r.status_code,
                "json": None,
                "text": None,
            }
            try:
                results[ep]["json"] = r.json()
            except Exception:
                results[ep]["text"] = r.text[:1000]
        except Exception as e:
            results[ep] = {"error": str(e)}
    return results


def try_lmstudio_client(host):
    try:
        import lmstudio as lms
    except Exception as e:
        return {"lmstudio_client": f"not available: {e}"}

    out = {}
    host_clean = host.replace("http://", "").replace("https://", "")
    try:
        lms.configure_default_client(host_clean)
        out["configured"] = host_clean
    except Exception as e:
        out["configure_error"] = str(e)

    # Try listing attributes to help user see what is available
    out["available_attributes"] = [a for a in dir(lms) if not a.startswith("_")]
    
    return out


def main():
    host = None
    if len(sys.argv) > 1:
        host = sys.argv[1]
    else:
        for h in DEFAULT_HOSTS:
            if h:
                host = h
                break
    if not host:
        print("No host provided and no SERVER_API_HOST/SERVER_IP env var found. Use: python list_lmstudio_models.py host:port")
        sys.exit(1)

    base = get_base_host(host)
    if not base:
        print("Invalid host.")
        sys.exit(1)

    print(f"Probing API host: {base}")
    results = try_endpoints(base)

    pretty = json.dumps(results, ensure_ascii=False, indent=2)
    print("\nHTTP endpoint probes (first 1000 chars of text responses shown):\n")
    print(pretty)

    print("\nAttempting lmstudio client calls (if installed):\n")
    try:
        client_res = try_lmstudio_client(base)
        print(json.dumps(client_res, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"lmstudio client attempt failed: {e}")

    # Save combined probe and client results to a JSON file for later inspection.
    out = {
        "probed_host": base,
        "http_probes": results,
        "lmstudio_client": client_res if 'client_res' in locals() else None,
        "generated_at": __import__('datetime').datetime.now().isoformat()
    }
    # Sanitize filename using host and timestamp
    host_for_filename = base.replace('http://', '').replace('https://', '').replace(':', '_').replace('/', '_')
    ts = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
    out_fname = f"probe_{host_for_filename}_{ts}.json"
    try:
        with open(out_fname, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print(f"\nSaved probe output to {out_fname}")
    except Exception as e:
        print(f"Failed to write probe output file: {e}")

    print("\nDone. Look through the JSON outputs above or the saved file to find available model names or engine ids.")


if __name__ == '__main__':
    main()
