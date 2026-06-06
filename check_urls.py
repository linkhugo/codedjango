#!/usr/bin/env python3
"""Lee URLs (http/https) desde un archivo, conecta a cada una y reporta el codigo HTTP.

Uso:
    python3 check_urls.py [archivo_urls]

Si no se indica archivo, se usa "urls.txt" por defecto.
Imprime los resultados en consola y los guarda en "resultados.csv".
"""

import csv
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "check-urls/1.0 (+https://example.local)"
TIMEOUT = 10  # segundos por URL


def leer_urls(ruta):
    """Devuelve la lista de URLs del archivo, ignorando lineas vacias y comentarios (#)."""
    urls = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            urls.append(linea)
    return urls


def normalizar(url):
    """Antepone https:// si la URL no trae esquema, como salvaguarda."""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def resolver_ip(url):
    """Devuelve la IP a la que resuelve el host de la URL, o None si no resuelve."""
    host = urllib.parse.urlparse(url).hostname
    if not host:
        return None
    try:
        # getaddrinfo soporta IPv4 e IPv6; tomamos la primera direccion resuelta.
        info = socket.getaddrinfo(host, None)
        return info[0][4][0]
    except (socket.gaierror, OSError):
        return None


def comprobar_url(url, timeout=TIMEOUT):
    """Conecta a la URL y devuelve (codigo, estado).

    codigo es el codigo HTTP (int) o None si no hubo respuesta del servidor.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, "OK"
    except urllib.error.HTTPError as e:
        # El servidor respondio con un codigo de error (404, 500, etc.)
        return e.code, e.reason
    except (socket.timeout, TimeoutError):
        return None, "Timeout"
    except urllib.error.URLError as e:
        # Fallo de conexion, DNS o SSL: no hay codigo HTTP
        return None, str(e.reason)
    except Exception as e:  # noqa: BLE001 - reportar cualquier otro fallo sin abortar
        return None, str(e)


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else "urls.txt"

    try:
        urls = leer_urls(ruta)
    except FileNotFoundError:
        print(f"No se encontro el archivo: {ruta}")
        sys.exit(1)

    if not urls:
        print(f"El archivo '{ruta}' no contiene URLs.")
        sys.exit(1)

    filas = []
    for url in urls:
        url = normalizar(url)
        ip = resolver_ip(url)
        codigo, estado = comprobar_url(url)
        codigo_txt = str(codigo) if codigo is not None else "ERR"
        ip_txt = ip if ip else "-"
        print(f"{codigo_txt:>4}  {ip_txt:<15}  {url}  ({estado})")
        filas.append([url, ip if ip else "", codigo if codigo is not None else "", estado])

    with open("resultados.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "ip", "codigo", "estado"])
        writer.writerows(filas)

    print(f"\nResultados guardados en resultados.csv ({len(filas)} URLs).")


if __name__ == "__main__":
    main()
