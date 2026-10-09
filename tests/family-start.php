<?php
declare(strict_types=1);
require __DIR__ . '/../module/src/FamilyStart.php';
use Openvoorouders\FamilyStart;
$people=FamilyStart::validate(['self'=>['given'=>'Gerhard','surname'=>'Westerman','birth'=>'abt 1900','source'=>'Familieverhaal'], 'father'=>['given'=>'Jan','birth'=>'1870']]);
assert(count($people)===2);
assert(str_contains(FamilyStart::gedcom($people['self']), '2 DATE ABT 1900'));
assert(str_contains(FamilyStart::gedcom($people['self']), 'Bron familiestart (nog te controleren): Familieverhaal'));
assert(!str_contains(FamilyStart::gedcom($people['father']),'DEAT'));
assert(FamilyStart::validate([])===[]);
foreach (["Jan\n1 DEAT", 'Jan @I1@', "Jan\0"] as $bad) {
    try {FamilyStart::validate(['self'=>['given'=>$bad]]);throw new Exception('GEDCOM-injectie geaccepteerd');} catch (InvalidArgumentException) {}
}
try {FamilyStart::validate(['self'=>['given'=>'Jan','birth'=>'gisteren']]);throw new Exception('Ongeldige datum geaccepteerd');} catch (InvalidArgumentException) {}
echo "Familiestart: onbekende gegevens, schattingen, bronnen en injectie gecontroleerd.\n";
