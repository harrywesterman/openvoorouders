<?php
declare(strict_types=1);
function e($value): string { return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
$details = ['job'=>['id'=>str_repeat('a',32),'state'=>'running'], 'messages'=>[
    ['info'=>['role'=>'user'], 'parts'=>[['type'=>'text','text'=>'Mijn vraag']]],
    ['info'=>['role'=>'assistant','authorization'=>'HIDDEN-AUTH'], 'parts'=>[
        ['type'=>'reasoning','text'=>'HIDDEN-REASONING'],
        ['type'=>'tool','tool'=>'webtrees_get-trees','state'=>['status'=>'completed','input'=>['query'=>'Zoek een bron'],'output'=>'<script>tool-output</script>']],
        ['type'=>'text','text'=>'<script>alert("xss")</script>'],
    ]],
]];
ob_start();require __DIR__.'/../module/resources/views/progress.phtml';$html=ob_get_clean();
assert(str_contains($html, 'webtrees_get-trees · Afgerond'));
assert(str_contains($html, '&lt;script&gt;'));
assert(!str_contains($html, '<script>'));
assert(!str_contains($html, 'HIDDEN-'));
assert(str_contains($html, 'Opdracht aan de tool'));
assert(str_contains($html, '&lt;script&gt;tool-output&lt;/script&gt;'));
$details['messages']=[];
ob_start();require __DIR__.'/../module/resources/views/progress.phtml';$html=ob_get_clean();
assert(str_contains($html, 'Er is nog geen zichtbare uitvoer'));
$details['job']['state']='complete';
ob_start();require __DIR__.'/../module/resources/views/progress.phtml';$html=ob_get_clean();
assert(str_contains($html, 'data-state="complete"'));
assert(!str_contains($html, 'Er is nog geen zichtbare uitvoer'));
echo "Veilige voortgangsweergave gecontroleerd.\n";
