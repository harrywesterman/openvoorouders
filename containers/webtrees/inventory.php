<?php
declare(strict_types=1);
// Do not execute unknown plugin PHP while checking upgrade compatibility.
$manifest = json_decode(file_get_contents('/opt/openvoorouders/release.json'), true, 512, JSON_THROW_ON_ERROR);
$managed = ['openvoorouders'];
foreach ($manifest['components'] as $component) if (!empty($component['folder'])) $managed[] = $component['folder'];
$config = parse_ini_file('/var/www/webtrees/data/config.ini.php');
if (!$config) throw new RuntimeException('Webtrees is nog niet ingericht.');
$prefix = $config['tblpfx'] ?? 'wt_';
if (!preg_match('/^[a-zA-Z0-9_]+$/', $prefix)) throw new RuntimeException('Ongeldig databaseprefix.');
$pdo = new PDO('mysql:host=database;dbname=webtrees', 'webtrees', trim(file_get_contents('/run/secrets/database')), [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$status = $pdo->query('SELECT module_name, status FROM ' . $prefix . 'module')->fetchAll(PDO::FETCH_KEY_PAIR);
$extra = [];
foreach (glob('/var/www/webtrees/modules_v4/*/module.php') as $path) {
    $name = basename(dirname($path));
    if (in_array($name, $managed, true)) continue;
    $root = dirname($path);
    $files = [];
    foreach (new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS)) as $file) {
        if ($file->isLink()) throw new RuntimeException('Aanvullende module bevat een link: ' . $name);
        if ($file->isFile()) $files[substr($file->getPathname(), strlen($root))] = hash_file('sha256', $file->getPathname());
    }
    ksort($files);
    $extra[] = ['name'=>$name, 'version'=>hash('sha256', json_encode($files)), 'enabled'=>($status['_' . $name . '_'] ?? 'enabled') !== 'disabled'];
}
echo json_encode($extra, JSON_THROW_ON_ERROR);
