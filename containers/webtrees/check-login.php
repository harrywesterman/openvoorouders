<?php
declare(strict_types=1);
// A reserved technical account has no tree role and no administrator rights.
// Its secret is never an export or a model input, and survives a complete snapshot.
$config = parse_ini_file('/var/www/webtrees/data/config.ini.php');
if (!$config) throw new RuntimeException('Webtrees-configuratie ontbreekt.');
$prefix = $config['tblpfx'] ?? 'wt_';
if (!preg_match('/^[a-zA-Z0-9_]+$/', $prefix)) throw new RuntimeException('Ongeldig prefix.');
$pdo = new PDO('mysql:host=database;dbname=webtrees', 'webtrees', trim(file_get_contents('/run/secrets/database')), [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$secret = '/opt/ovo-data/health-credentials.json';
if (!is_file($secret)) {
    $credentials = ['username'=>'ovo-health-' . bin2hex(random_bytes(5)), 'password'=>bin2hex(random_bytes(32))];
    file_put_contents($secret, json_encode($credentials, JSON_THROW_ON_ERROR));
    chmod($secret, 0600);
} else $credentials = json_decode(file_get_contents($secret), true, 512, JSON_THROW_ON_ERROR);
$query = $pdo->prepare('SELECT user_id FROM ' . $prefix . 'user WHERE user_name=?');
$query->execute([$credentials['username']]);
$id = $query->fetchColumn();
if (!$id) {
    $insert = $pdo->prepare('INSERT INTO ' . $prefix . 'user (user_name,real_name,email,password) VALUES (?,?,?,?)');
    $insert->execute([$credentials['username'], 'Openvoorouders healthcheck', $credentials['username'].'@openvoorouders.invalid', password_hash($credentials['password'], PASSWORD_DEFAULT)]);
    $id = $pdo->lastInsertId();
    $setting = $pdo->prepare('INSERT INTO ' . $prefix . 'user_setting (user_id,setting_name,setting_value) VALUES (?,?,?)');
    foreach (['verified'=>'1','verified_by_admin'=>'1','canadmin'=>'0','auto_accept'=>'0'] as $key=>$value) $setting->execute([$id,$key,$value]);
}
$jar = tempnam(sys_get_temp_dir(), 'ovo-login-');
$curl = curl_init();
curl_setopt_array($curl, [CURLOPT_RETURNTRANSFER=>true, CURLOPT_COOKIEJAR=>$jar, CURLOPT_COOKIEFILE=>$jar, CURLOPT_TIMEOUT=>30, CURLOPT_USERAGENT=>'Openvoorouders healthcheck']);
try {
    curl_setopt($curl, CURLOPT_URL, 'http://127.0.0.1/login');
    $page = curl_exec($curl);
    if (!is_string($page) || !preg_match('/name="_csrf"[^>]*value="([^"]+)"/', $page, $match)) throw new RuntimeException('Inlogformulier werkt niet.');
    curl_setopt($curl, CURLOPT_POST, true);
    curl_setopt($curl, CURLOPT_POSTFIELDS, http_build_query(['username'=>$credentials['username'], 'password'=>$credentials['password'], '_csrf'=>html_entity_decode($match[1]), 'url'=>rtrim(getenv('BASE_URL') ?: 'http://127.0.0.1','/') . '/my-account']));
    curl_exec($curl);
    if (curl_getinfo($curl, CURLINFO_RESPONSE_CODE) !== 302) throw new RuntimeException('Inloggen werkt niet.');
    curl_setopt($curl, CURLOPT_HTTPGET, true);
    curl_setopt($curl, CURLOPT_URL, 'http://127.0.0.1/my-account');
    $page = curl_exec($curl);
    if (curl_getinfo($curl, CURLINFO_RESPONSE_CODE) !== 200 || !str_contains((string)$page, 'name="email"') || !str_contains((string)$page, $credentials['username'])) throw new RuntimeException('Aangemelde sessie werkt niet.');
} finally { curl_close($curl); unlink($jar); }
echo "Database en echte webtrees-login gecontroleerd.\n";
