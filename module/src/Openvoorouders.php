<?php
declare(strict_types=1);
namespace Openvoorouders;

use Fisharebest\Webtrees\Auth;
use Fisharebest\Webtrees\DB;
use Fisharebest\Webtrees\Menu;
use Fisharebest\Webtrees\Tree;
use Fisharebest\Webtrees\View;
use Fisharebest\Webtrees\Registry;
use Fisharebest\Webtrees\Contracts\UserInterface;
use Fisharebest\Webtrees\Http\ViewResponseTrait;
use Fisharebest\Webtrees\Http\Exceptions\HttpAccessDeniedException;
use Fisharebest\Webtrees\Module\AbstractModule;
use Fisharebest\Webtrees\Module\ModuleCustomInterface;
use Fisharebest\Webtrees\Module\ModuleCustomTrait;
use Fisharebest\Webtrees\Module\ModuleMenuInterface;
use Fisharebest\Webtrees\Module\ModuleMenuTrait;
use Fisharebest\Webtrees\Services\TreeService;
use Fisharebest\Webtrees\Services\UserService;
use Fisharebest\Webtrees\Services\GedcomImportService;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Jefferson49\Webtrees\Module\WebtreesApi\WebtreesApi;
use Jefferson49\Webtrees\Module\WebtreesApi\OAuth2\Client;
use Jefferson49\Webtrees\Module\WebtreesApi\OAuth2\AccessToken;
use Jefferson49\Webtrees\Module\WebtreesApi\OAuth2\Repositories\ClientRepository;
use Jefferson49\Webtrees\Module\WebtreesApi\OAuth2\Repositories\ScopeRepository;
use Jefferson49\Webtrees\Module\WebtreesApi\OAuth2\Repositories\AccessTokenRepository;
use League\OAuth2\Server\CryptKey;

final class Openvoorouders extends AbstractModule implements ModuleCustomInterface, ModuleMenuInterface
{
    use ModuleCustomTrait;
    use ModuleMenuTrait;
    use ViewResponseTrait;

    public function title(): string { return 'Openvoorouders'; }
    public function description(): string { return 'Nederlands stamboomonderzoek met bronnen en AI.'; }
    public function customModuleVersion(): string {
        $file = '/opt/openvoorouders/release.json';
        return is_file($file) ? (json_decode(file_get_contents($file), true)['version'] ?? 'development') : 'development';
    }
    public function customModuleAuthorName(): string { return 'Openvoorouders'; }
    public function resourcesFolder(): string { return __DIR__ . '/../resources/'; }
    public function boot(): void { View::registerNamespace('openvoorouders', $this->resourcesFolder() . 'views/'); }
    public function url(array $params = []): string {
        return route('module-no-tree', ['module'=>$this->name(), 'action'=>'AdminResearch'] + $params);
    }
    public function getMenu(Tree $tree): ?Menu {
        return Auth::isAdmin() ? new Menu('Onderzoek', $this->url()) : null;
    }

    private function owner(ServerRequestInterface $request): UserInterface
    {
        $user = $request->getAttribute('user');
        if (!$user || !Auth::isAdmin($user) || ($this->getPreference('owner') !== '' && $this->getPreference('owner') !== (string) $user->id())) {
            throw new HttpAccessDeniedException('Alleen de ingestelde onderzoeker heeft toegang.');
        }
        return $user;
    }
    private function tree(): ?Tree {
        foreach (Registry::container()->get(TreeService::class)->all() as $tree) {
            if ((string) $tree->id() === $this->getPreference('tree')) return $tree;
        }
        return null;
    }
    private function data(): string { return getenv('OVO_DATA') ?: '/opt/ovo-data'; }

    private function agent(string $method, string $path, array $body = []): array
    {
        $key = trim(file_get_contents('/run/secrets/agent'));
        $context = stream_context_create(['http'=>['method'=>$method, 'timeout'=>120, 'ignore_errors'=>true,
            'header'=>"Content-Type: application/json\r\nAuthorization: Bearer " . $key,
            'content'=>$method === 'GET' ? '' : json_encode($body, JSON_THROW_ON_ERROR)]]);
        $raw = @file_get_contents((getenv('OVO_AGENT_URL') ?: 'http://agent:4080') . $path, false, $context);
        if ($raw === false) throw new \RuntimeException('De onderzoeksagent is niet bereikbaar.');
        $result = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
        if (isset($result['error'])) throw new \RuntimeException($result['error']);
        return is_array($result) ? $result : [];
    }

    /** Generate a short-lived token for an editor that can never approve its own writes. */
    private function token(Tree $tree, bool $private): string
    {
        $api = Registry::container()->get(WebtreesApi::class);
        $api->initializeKeys();
        $users = Registry::container()->get(UserService::class);
        $editor = $users->findByUserName('openvoorouders-editor');
        if ($editor === null) $editor = $users->create('openvoorouders-editor', 'Openvoorouders onderzoeksagent', 'agent@openvoorouders.invalid', bin2hex(random_bytes(32)));
        $editor->setPreference(UserInterface::PREF_IS_ADMINISTRATOR, '0');
        $editor->setPreference(UserInterface::PREF_AUTO_ACCEPT_EDITS, '0');
        $editor->setPreference(UserInterface::PREF_IS_EMAIL_VERIFIED, '1');
        $editor->setPreference(UserInterface::PREF_IS_ACCOUNT_APPROVED, '1');
        foreach (Registry::container()->get(TreeService::class)->all() as $other) {
            $other->setUserPreference($editor, UserInterface::PREF_TREE_ROLE, $other->id() === $tree->id() ? UserInterface::ROLE_EDITOR : 'none');
        }
        $scopes = Registry::container()->get(ScopeRepository::class)->getScopesForIdentifiers([$private ? 'mcp_read_member' : 'mcp_read_privacy', 'mcp_write']);
        $clients = new ClientRepository();
        $id = $private ? 'openvoorouders-private' : 'openvoorouders-public';
        $clients->removeClient($id);
        $clients->addClient(new Client($id, $id, password_hash(bin2hex(random_bytes(32)), PASSWORD_DEFAULT), $scopes, ['client_credentials'], $editor->id()));
        $api->setPreference(WebtreesApi::PREF_ALLOW_MCP_READ_MEMBER, $private ? '1' : '0');
        $repository = Registry::container()->get(AccessTokenRepository::class);
        $token = $repository->getNewToken($clients->getClientEntity($id), $scopes, null, 'P1D');
        $token->setPrivateKey(new CryptKey($api->getKeyPath(true)));
        $long = $token->toString();
        $token->setCreatedInControlPanel();
        $token->setShortToken(AccessToken::createShortToken($long));
        $repository->persistNewAccessToken($token);
        return $long;
    }

    public function getAdminResearchAction(ServerRequestInterface $request): ResponseInterface
    {
        $this->owner($request);
        $query = $request->getQueryParams();
        $tab = (string) ($query['tab'] ?? 'onderzoek');
        if (($query['progress'] ?? '') === '1') {
            $id = (string) ($query['job'] ?? '');
            if (!preg_match('/^[a-f0-9]{32}$/', $id)) return response('Ongeldig onderzoek.', 400);
            try {
                $details = $this->agent('GET', '/jobs/' . $id);
                return response(view('openvoorouders::progress', ['details'=>$details]), 200)
                    ->withHeader('Cache-Control', 'no-store');
            } catch (\Throwable $e) {
                return response('De voortgang is tijdelijk niet beschikbaar.', 503)->withHeader('Cache-Control', 'no-store');
            }
        }
        $model = $jobs = $details = $settings = $consents = [];
        $error = '';
        try {
            if ($tab === 'onderzoek') {
                $model = $this->agent('GET', '/providers');
                $jobs = $this->agent('GET', '/jobs');
                if (preg_match('/^[a-f0-9]{32}$/', (string) ($query['job'] ?? ''))) $details = $this->agent('GET', '/jobs/' . $query['job']);
            }
            if ($tab === 'instellingen') {
                $model = $this->agent('GET', '/providers');
                $settings = $this->agent('GET', '/auth-methods');
                $consents = $this->agent('GET', '/consent');
            }
        } catch (\Throwable $e) { $error = $e->getMessage(); }
        $draft = json_decode(@file_get_contents($this->data() . '/family-start.json') ?: '{}', true);
        $release = json_decode(file_get_contents('/opt/openvoorouders/release.json'), true);
        return $this->viewResponse('openvoorouders::page', ['title'=>'Openvoorouders', 'module'=>$this,
            'tree'=>$this->tree(), 'trees'=>Registry::container()->get(TreeService::class)->all(), 'tab'=>$tab,
            'providers'=>$model, 'jobs'=>$jobs, 'details'=>$details, 'methods'=>$settings, 'consents'=>$consents,
            'draft'=>$draft, 'release'=>$release, 'error'=>$error, 'message'=>(string) ($query['message'] ?? '')]);
    }

    public function postAdminResearchAction(ServerRequestInterface $request): ResponseInterface
    {
        $user = $this->owner($request);
        $body = $request->getParsedBody();
        $tree = $this->tree();
        $tab = (string) ($body['tab'] ?? 'onderzoek');
        try {
            $maintenance = json_decode(@file_get_contents('/opt/ovo-control/maintenance.json') ?: '{"enabled":true}', true);
            if ($maintenance['enabled'] ?? true) throw new \RuntimeException('Openvoorouders wordt bijgewerkt.');
            switch ($body['do'] ?? '') {
                case 'create-tree':
                    if ($tree !== null) throw new \RuntimeException('De actieve boom is al ingesteld.');
                    $title = trim((string) ($body['title'] ?? 'Mijn stamboom'));
                    if ($title === '' || mb_strlen($title) > 100) throw new \InvalidArgumentException('Geef een stamboomnaam van maximaal 100 tekens.');
                    DB::connection()->transaction(function () use ($title, $user): void {
                        $new = Registry::container()->get(TreeService::class)->create('openvoorouders-' . bin2hex(random_bytes(6)), $title);
                        // Native creation inserts a sample person. Remove only this newly created
                        // sample, in the same transaction, through webtrees' own index maintenance.
                        $sample = Registry::individualFactory()->make('X1', $new);
                        if (!$sample) throw new \RuntimeException('De nieuwe stamboom kon niet worden voorbereid.');
                        Registry::container()->get(GedcomImportService::class)->updateRecord($sample->gedcom(), $new, true);
                        $this->selectTree($new, $user);
                    });
                    return redirect($this->url(['tab'=>'familiestart']));
                case 'custom-provider':
                    $this->agent('POST', '/providers/custom', ['provider'=>(string)$body['provider'], 'name'=>(string)$body['name'],
                        'url'=>(string)$body['url'], 'model'=>(string)$body['model'], 'key'=>(string)($body['key'] ?? ''),
                        'context'=>(int)$body['context'], 'output'=>(int)$body['output'], 'tools'=>isset($body['tools']), 'image'=>isset($body['image'])]);
                    break;
                case 'export':
                    if (!$tree) throw new \RuntimeException('Kies eerst een stamboom.');
                    return $this->downloadExport($tree);
                case 'configure':
                    if ($tree !== null) throw new \RuntimeException('De actieve boom is al ingesteld.');
                    foreach (Registry::container()->get(TreeService::class)->all() as $candidate) {
                        if ((string) $candidate->id() === (string) ($body['tree'] ?? '')) {
                            $this->selectTree($candidate, $user);
                            break;
                        }
                    }
                    if (!$this->tree()) throw new \RuntimeException('Kies eerst je actieve stamboom.');
                    break;
                case 'draft':
                    $people = FamilyStart::validate($body['people'] ?? []);
                    $this->saveDraft(['people'=>$people, 'review'=>isset($body['review']), 'saved'=>false]);
                    break;
                case 'save-family':
                    if (!$tree) throw new \RuntimeException('Kies eerst een stamboom.');
                    $this->saveFamily($tree, (string) ($body['draft_hash'] ?? ''));
                    break;
                case 'research':
                    if (!$tree) throw new \RuntimeException('Kies eerst een stamboom.');
                    $gate = fopen($this->data() . '/research.lock', 'c');
                    if (!$gate || !flock($gate, LOCK_EX | LOCK_NB)) throw new \RuntimeException('Er start al een onderzoek.');
                    try {
                    if ($this->agent('GET', '/internal/status')['busy']) throw new \RuntimeException('Er loopt al onderzoek.');
                    $private = isset($body['private']);
                    // Check consent before ever enabling/minting the member scope.
                    $consent = $this->agent('GET', '/consent');
                    if ($private && !($consent[$body['provider'] ?? ''] ?? false)) throw new \RuntimeException('Geef eerst toestemming voor privégegevens bij deze provider.');
                    $job = $this->agent('POST', '/research', ['provider'=>(string) $body['provider'], 'model'=>(string) $body['model'],
                        'private'=>$private, 'prompt'=>(string) $body['prompt'], 'continue'=>(string) ($body['continue'] ?? ''),
                        'tree'=>$tree->name(), 'webtrees_token'=>$this->token($tree, $private)]);
                    } finally { flock($gate, LOCK_UN); fclose($gate); }
                    return redirect($this->url(['job'=>$job['id']]));
                case 'stop':
                    if (!preg_match('/^[a-f0-9]{32}$/', (string) $body['job'])) throw new \RuntimeException('Ongeldig onderzoek.');
                    $this->agent('POST', '/jobs/' . $body['job'] . '/stop');
                    break;
                case 'consent':
                    $this->agent('POST', '/consent', ['provider'=>(string) $body['provider'], 'enabled'=>isset($body['enabled'])]);
                    Registry::container()->get(WebtreesApi::class)->setPreference(WebtreesApi::PREF_ALLOW_MCP_READ_MEMBER, '0');
                    break;
                case 'key':
                case 'oauth':
                case 'callback':
                    if (!preg_match('/^[a-zA-Z0-9_.-]+$/', (string) $body['provider'])) throw new \RuntimeException('Ongeldige provider.');
                    $result = $this->agent('POST', '/providers/' . $body['provider'] . '/' . $body['do'],
                        $body['do'] === 'key' ? ['key'=>(string) $body['key']] : ($body['do'] === 'oauth'
                            ? ['method'=>(int) $body['method'], 'inputs'=>array_map('strval', (array) ($body['inputs'] ?? []))]
                            : ['method'=>(int) $body['method'], 'code'=>(string) ($body['code'] ?? '')]));
                    if (isset($result['url'])) {
                        // Render the native authorization URL, never redirect credentials to an arbitrary proxy.
                        return $this->viewResponse('openvoorouders::oauth', ['title'=>'Provider verbinden', 'module'=>$this,
                            'authorization'=>$result, 'provider'=>(string) $body['provider'], 'method'=>(int) $body['method']]);
                    }
                    break;
                default: throw new \RuntimeException('Onbekende actie.');
            }
            return redirect($this->url(['tab'=>$tab, 'message'=>'Opgeslagen.']));
        } catch (\Throwable $e) {
            // No raw engine/database exceptions or credentials in URLs or browser output.
            $message = $e instanceof \RuntimeException || $e instanceof \InvalidArgumentException ? $e->getMessage() : 'De actie is mislukt. Controleer de koppeling of je invoer.';
            return response('<p>' . e($message) . '</p><a href="' . e($this->url(['tab'=>$tab])) . '">Terug naar Openvoorouders</a>', 400);
        }
    }

    private function selectTree(Tree $tree, UserInterface $user): void {
        $this->setPreference('owner', (string) $user->id());
        $this->setPreference('tree', (string) $tree->id());
        $user->setPreference(UserInterface::PREF_THEME, '_jc-theme-justlight_');
        $user->setPreference(UserInterface::PREF_LANGUAGE, 'nl');
    }

    private function saveDraft(array $draft): void {
        $file = $this->data() . '/family-start.json';
        $temp = $file . '.' . bin2hex(random_bytes(8));
        file_put_contents($temp, json_encode($draft, JSON_THROW_ON_ERROR));
        chmod($temp, 0660);
        rename($temp, $file);
    }

    public function dossiers(): array {
        $files = [];
        foreach (['public','private'] as $profile) {
            $base = $this->data() . '/' . $profile . '/dossiers';
            if (!is_dir($base)) continue;
            foreach (new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator($base, \FilesystemIterator::SKIP_DOTS)) as $file) {
                if (!$file->isLink() && $file->isFile() && $file->getExtension() === 'md' && $file->getSize() < 1024 * 1024) {
                    $real = realpath($file->getPathname());
                    if ($real && str_starts_with($real, realpath($base) . DIRECTORY_SEPARATOR)) {
                        $files[$profile . '/' . substr($real, strlen(realpath($base)) + 1)] = file_get_contents($real);
                    }
                }
            }
        }
        ksort($files);
        return $files;
    }

    private function downloadExport(Tree $tree): ResponseInterface {
        if ($this->agent('GET', '/internal/status')['busy']) throw new \RuntimeException('Rond onderzoek eerst af voor een export.');
        $file = tempnam(sys_get_temp_dir(), 'ovo-export-');
        $zip = new \ZipArchive();
        if ($zip->open($file, \ZipArchive::OVERWRITE) !== true) throw new \RuntimeException('Exportbestand kan niet worden gemaakt.');
        try {
            $gedcom = "0 HEAD\n1 SOUR Openvoorouders\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n";
            DB::connection()->transaction(function () use ($tree, &$gedcom, $zip): void {
                foreach (['individuals'=>'i','families'=>'f','sources'=>'s','media'=>'m','other'=>'o'] as $table=>$prefix) {
                    foreach (DB::table($table)->where($prefix . '_file', $tree->id())->pluck($prefix . '_gedcom') as $record) {
                        if (!preg_match('/^0 (HEAD|TRLR)/', (string) $record)) $gedcom .= trim((string)$record) . "\n";
                    }
                }
                $zip->addFromString('pending-wijzigingen.json', json_encode(DB::table('change')->where('gedcom_id', $tree->id())->where('status','pending')->get(), JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
            });
            $zip->addFromString('stamboom.ged', $gedcom . "0 TRLR\n");
            $research = $this->agent('GET','/export');
            $zip->addFromString('gesprekken.json', json_encode($research['conversations'], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
            foreach ($research['dossiers'] as $name=>$content) {
                if (str_contains($name, '..') || str_starts_with($name, '/')) throw new \RuntimeException('Ongeldig dossierpad.');
                $zip->addFromString('dossiers/' . $name, $content);
            }
            $draft = $this->data() . '/family-start.json';
            if (is_file($draft)) $zip->addFile($draft, 'familiestart.json');
            $size = 0;
            foreach (['media'=>realpath('/var/www/webtrees/data/' . $tree->mediaFolder()),
                'scans-public'=>realpath($this->data() . '/public/scans'), 'scans-private'=>realpath($this->data() . '/private/scans')] as $name=>$folder) {
                if (!$folder) continue;
                $safe = $name === 'media' ? realpath('/var/www/webtrees/data') : realpath($this->data());
                if (!$safe || !str_starts_with($folder, $safe . DIRECTORY_SEPARATOR)) throw new \RuntimeException('Media staan buiten de beheerde gegevensmap.');
                foreach (new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator($folder, \FilesystemIterator::SKIP_DOTS)) as $entry) {
                    if ($entry->isLink()) throw new \RuntimeException('Exporteer media zonder symbolische links.');
                    if (!$entry->isFile()) continue;
                    $size += $entry->getSize();
                    if ($size > 500 * 1024 * 1024) throw new \RuntimeException('Deze export is groter dan 500 MiB. Gebruik de lokale back-up of een aparte media-export.');
                    $zip->addFile($entry->getPathname(), $name . '/' . substr($entry->getPathname(), strlen($folder) + 1));
                }
            }
            $zip->addFromString('LEESMIJ.txt', 'Persoonlijke export: stamboom, media, dossiers, gesprekken en voorstellen. Geen authenticatieopslag, sleutels of database-instellingen. Voor volledig herstel gebruikt de beheerder de lokale back-up.');
            if (!$zip->close()) throw new \RuntimeException('Export is onvolledig.');
            return response()->withBody(\GuzzleHttp\Psr7\Utils::streamFor(fopen($file,'rb')))
                ->withHeader('Content-Type','application/zip')->withHeader('Content-Disposition','attachment; filename="openvoorouders-export.zip"')->withHeader('Cache-Control','no-store');
        } finally { @unlink($file); }
    }

    private function saveFamily(Tree $tree, string $expected): void {
        $handle = fopen($this->data() . '/family-start.lock', 'c');
        if (!$handle || !flock($handle, LOCK_EX)) throw new \RuntimeException('De familiestart is tijdelijk bezet.');
        try {
            $draft = json_decode(file_get_contents($this->data() . '/family-start.json'), true, 512, JSON_THROW_ON_ERROR);
            if (!hash_equals(hash('sha256', json_encode($draft, JSON_THROW_ON_ERROR)), $expected)) throw new \RuntimeException('Het concept is gewijzigd. Bekijk het controleoverzicht opnieuw.');
            if (!$draft['review'] || $draft['saved'] || !isset($draft['people']['self'])) throw new \RuntimeException('Controleer eerst de beginpersoon en familiegegevens.');
            DB::connection()->transaction(function () use ($tree, $draft): void {
                // Lock the tree row: concurrent/replayed submissions cannot create a second family.
                DB::table('gedcom')->where('gedcom_id', $tree->id())->lockForUpdate()->first();
                if (DB::table('individuals')->where('i_file', $tree->id())->exists() || DB::table('change')->where('gedcom_id', $tree->id())->exists()) {
                    throw new \RuntimeException('Deze boom bevat al personen of voorstellen. Gebruik de bestaande webtrees-invoer.');
                }
                $records = [];
                $gedcom = [];
                foreach ($draft['people'] as $role => $person) {
                    $gedcom[$role] = FamilyStart::gedcom($person);
                    $records[$role] = $tree->createIndividual($gedcom[$role]);
                    $gedcom[$role] = str_replace('0 @@ INDI', '0 @' . $records[$role]->xref() . '@ INDI', $gedcom[$role]);
                }
                foreach ([['self','father','mother'], ['father','ff','fm'], ['mother','mf','mm'],
                    ['ff','fff','ffm'], ['fm','fmf','fmm'], ['mf','mff','mfm'], ['mm','mmf','mmm']] as [$child,$father,$mother]) {
                    if (!isset($records[$child]) || (!isset($records[$father]) && !isset($records[$mother]))) continue;
                    $family = '0 @@ FAM' . "\n1 CHIL @" . $records[$child]->xref() . '@';
                    if (isset($records[$father])) $family .= "\n1 HUSB @" . $records[$father]->xref() . '@';
                    if (isset($records[$mother])) $family .= "\n1 WIFE @" . $records[$mother]->xref() . '@';
                    $record = $tree->createRecord($family);
                    foreach ([$child=>'FAMC', $father=>'FAMS', $mother=>'FAMS'] as $role=>$tag) {
                        if (!isset($records[$role])) continue;
                        $gedcom[$role] .= "\n1 " . $tag . ' @' . $record->xref() . '@';
                        $records[$role]->updateRecord($gedcom[$role], true);
                    }
                }
            });
            $draft['saved'] = true;
            $this->saveDraft($draft);
        } finally { flock($handle, LOCK_UN); fclose($handle); }
    }
}
