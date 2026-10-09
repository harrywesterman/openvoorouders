<?php
declare(strict_types=1);

/** Follow native tree redirects, while connecting to the container loopback. */
function ovoProbe(): CurlHandle {
    $base = rtrim(getenv('BASE_URL') ?: 'http://127.0.0.1', '/');
    $url = parse_url($base);
    if (($url['scheme'] ?? '') !== 'http' || empty($url['host'])) {
        throw new RuntimeException('De lokale controle vereist het ingestelde HTTP-basisadres.');
    }
    $curl = curl_init();
    curl_setopt_array($curl, [
        CURLOPT_RETURNTRANSFER=>true, CURLOPT_TIMEOUT=>30,
        CURLOPT_USERAGENT=>'Openvoorouders healthcheck',
        CURLOPT_CONNECT_TO=>[$url['host'] . ':' . ($url['port'] ?? 80) . ':127.0.0.1:80'],
        CURLOPT_PROXY=>'', CURLOPT_FOLLOWLOCATION=>true, CURLOPT_MAXREDIRS=>5,
        CURLOPT_REDIR_PROTOCOLS=>CURLPROTO_HTTP,
        CURLOPT_URL=>$base . '/login',
    ]);
    return $curl;
}
