<?php
declare(strict_types=1);
namespace Openvoorouders;

/** Pure validation/GEDCOM conversion; no AI and no writes during preview. */
final class FamilyStart
{
    public const ROLES = ['self'=>'Beginpersoon', 'father'=>'Vader', 'mother'=>'Moeder',
        'ff'=>'Vaders vader', 'fm'=>'Vaders moeder', 'mf'=>'Moeders vader', 'mm'=>'Moeders moeder',
        'fff'=>'Vader van vaders vader', 'ffm'=>'Moeder van vaders vader', 'fmf'=>'Vader van vaders moeder', 'fmm'=>'Moeder van vaders moeder',
        'mff'=>'Vader van moeders vader', 'mfm'=>'Moeder van moeders vader', 'mmf'=>'Vader van moeders moeder', 'mmm'=>'Moeder van moeders moeder'];

    public static function validate(array $input): array
    {
        $result = [];
        foreach (self::ROLES as $role => $label) {
            $person = [];
            foreach (['given', 'surname', 'birth', 'place', 'death', 'source', 'note'] as $field) {
                $raw = (string) ($input[$role][$field] ?? '');
                $value = trim($raw);
                if (strlen($value) > 1000 || preg_match('/[\r\n\x00-\x1F@]/', $raw)) {
                    throw new \InvalidArgumentException('Gebruik één tekstregel zonder GEDCOM-codes bij ' . $label . '.');
                }
                $person[$field] = $value;
            }
            foreach (['birth', 'death'] as $field) {
                if ($person[$field] !== '' && !preg_match('/^(?:(?:ABT|BEF|AFT) )?(?:\d{1,2} (?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC) )?\d{3,4}$/', strtoupper($person[$field]))) {
                    throw new \InvalidArgumentException('Gebruik een jaar, ABT 1900 (ongeveer), BEF 1900, AFT 1900 of 12 JAN 1900. Laat onbekende datums leeg.');
                }
                $person[$field] = strtoupper($person[$field]);
            }
            $known = count(array_filter($person, static fn(string $value): bool => $value !== '')) > 0;
            $person['sex'] = $role === 'self' ? 'U' : ($role === 'father' || str_ends_with($role, 'f') ? 'M' : 'F');
            if ($known) $result[$role] = $person;
        }
        return $result;
    }

    public static function gedcom(array $p): string
    {
        $text = '0 @@ INDI' . "\n1 NAME " . $p['given'] . ' /' . str_replace('/', '', $p['surname']) . "/\n1 SEX " . $p['sex'];
        if ($p['birth'] !== '' || $p['place'] !== '') {
            $text .= "\n1 BIRT";
            if ($p['birth'] !== '') $text .= "\n2 DATE " . $p['birth'];
            if ($p['place'] !== '') $text .= "\n2 PLAC " . $p['place'];
        }
        if ($p['death'] !== '') $text .= "\n1 DEAT\n2 DATE " . $p['death'];
        if ($p['source'] !== '') $text .= "\n1 NOTE Bron familiestart (nog te controleren): " . $p['source'];
        if ($p['note'] !== '') $text .= "\n1 NOTE " . $p['note'];
        return $text;
    }
}
