<?php
declare(strict_types=1);
// This check intentionally verifies HTTP rendering and plugin installation, not merely Apache.
require_once __DIR__ . '/http-probe.php';
$probe = ovoProbe();
$body = curl_exec($probe);
curl_close($probe);
if ($body === false || !str_contains(strtolower($body), '<html')) {
    throw new RuntimeException('Webtrees geeft geen bruikbare pagina terug.');
}
$manifest = json_decode(file_get_contents('/opt/openvoorouders/release.json'), true, 512, JSON_THROW_ON_ERROR);
foreach ($manifest['components'] as $component) {
    if (!empty($component['folder']) && !is_file('/var/www/webtrees/modules_v4/' . $component['folder'] . '/module.php')) {
        throw new RuntimeException('Een gebundelde module ontbreekt: ' . $component['folder']);
    }
}
echo "Website en gebundelde modules bereikbaar.\n";
require __DIR__ . '/check-login.php';
