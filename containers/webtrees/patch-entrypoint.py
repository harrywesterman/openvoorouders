"""Make the pinned upstream setup wait for Apache's listening socket."""
from pathlib import Path

path = Path('/docker-entrypoint.py')
source = path.read_text()
needle = '        # check status code\n'
if source.count(needle) != 1:
    raise RuntimeError('Het upstream-opstartscript is gewijzigd; beoordeel de readiness-patch opnieuw.')
source = source.replace(needle, '        except urllib.error.URLError:\n            time.sleep(1)\n            continue\n\n' + needle)
foreground = '    subprocess.run(["apache2-foreground"], stderr=subprocess.DEVNULL)'
if source.count(foreground) != 1:
    raise RuntimeError('Het upstream-procesbeheer is gewijzigd; beoordeel de afsluitpatch opnieuw.')
source = source.replace(foreground, '    os.execvp("apache2-foreground", ["apache2-foreground"])')
compile(source, str(path), 'exec')
path.write_text(source)
