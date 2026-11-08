<?php
// Optional CLI-only demo setup against the installed Pelican service interfaces.
// Password arrives on stdin, never in argv. Run as www-data in the panel directory.
if (PHP_SAPI !== 'cli') { exit(1); }
$input = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
chdir('/var/www/pelican');
require 'vendor/autoload.php';
$app = require 'bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
set_exception_handler(static function (Throwable $error): never {
    $detail = get_class($error) === RuntimeException::class ? $error->getMessage() : get_class($error);
    if ($error instanceof Illuminate\Validation\ValidationException) {
        $detail .= ' fields: ' . implode(', ', array_keys($error->errors()));
    }
    fwrite(STDERR, 'Fogata setup failed: ' . $detail . PHP_EOL);
    exit(1);
});
config(['panel.email.send_account_created_notification' => false, 'mail.default' => 'log']);

if (($input['phase'] ?? '') === 'base') {
    if (strlen($input['adminPassword'] ?? '') < 20) { throw new RuntimeException('Strong admin password required'); }
    $user = App\Models\User::where('username', 'admin')->first();
    if (!$user) {
        $user = app(App\Services\Users\UserCreationService::class)->handle([
            'username' => 'admin', 'email' => 'admin@fogata.invalid',
            'password' => $input['adminPassword'], 'root_admin' => true,
        ]);
    }
    $node = App\Models\Node::firstOrCreate(['name' => 'Fogata'], [
        'description' => 'Single-node Azure demo', 'fqdn' => $input['hostname'],
        'scheme' => 'https', 'behind_proxy' => true, 'public' => false,
        'maintenance_mode' => false, 'memory' => 6144, 'memory_overallocate' => 0,
        'disk' => 40000, 'disk_overallocate' => 0, 'cpu' => 200, 'cpu_overallocate' => 0,
        'upload_size' => 256, 'daemon_listen' => 8080, 'daemon_connect' => 8443,
        'daemon_sftp' => 2022, 'daemon_base' => '/var/lib/pelican/volumes',
    ]);
    App\Models\Allocation::firstOrCreate(['node_id' => $node->id, 'ip' => '0.0.0.0', 'port' => 25565]);
    if (!App\Models\Egg::where('name', 'like', '%Paper%')->exists()) {
        if (Illuminate\Support\Facades\Artisan::call('p:egg:update-index') !== 0) {
            throw new RuntimeException('Could not retrieve official egg index');
        }
        $url = null;
        foreach (cache()->get('eggs.index', []) as $eggs) {
            foreach ($eggs as $download => $name) {
                if (strcasecmp($name, 'Paper') === 0) { $url = $download; break 2; }
            }
        }
        if (!$url) { throw new RuntimeException('Paper not found in official egg index'); }
        app(App\Services\Eggs\Sharing\EggImporterService::class)->fromUrl($url);
    }
    $cfg = $node->getConfiguration();
    $cfg['api']['host'] = '127.0.0.1';
    $cfg['api']['ssl']['enabled'] = false;
    $cfg['ignore_panel_config_updates'] = true;
    $path = storage_path('app/fogata-wings.yml');
    $cfg = json_decode(json_encode($cfg, JSON_THROW_ON_ERROR), true, 512, JSON_THROW_ON_ERROR);
    file_put_contents($path, Symfony\Component\Yaml\Yaml::dump($cfg, 10, 2, Symfony\Component\Yaml\Yaml::DUMP_EMPTY_ARRAY_AS_SEQUENCE));
    chmod($path, 0600);
    $env = file_get_contents('.env');
    $env = preg_replace('/^APP_INSTALLED=.*$/m', 'APP_INSTALLED=true', $env);
    file_put_contents('.env', $env);
    echo json_encode(['admin' => 'admin', 'nodeId' => $node->id, 'egg' => 'Paper']) . PHP_EOL;
} elseif (($input['phase'] ?? '') === 'server') {
    if (($input['acceptMinecraftEula'] ?? false) !== true) { throw new RuntimeException('EULA acceptance required'); }
    $server = App\Models\Server::where('name', 'Fogata - Prueba')->first();
    if (!$server) {
        $egg = App\Models\Egg::where('name', 'like', '%Paper%')->firstOrFail();
        $node = App\Models\Node::where('name', 'Fogata')->firstOrFail();
        $allocation = App\Models\Allocation::where('node_id', $node->id)->where('port', 25565)->firstOrFail();
        $environment = [];
        foreach ($egg->variables as $variable) { $environment[$variable->env_variable] = $variable->default_value; }
        $environment['USER_AGENT'] = 'Fogata/0.1 (+' . ($input['portalUrl'] ?? 'https://localhost') . ')';
        $image = null;
        foreach ($egg->docker_images as $label => $candidate) {
            if (str_contains((string)$label, '25') || str_contains($candidate, 'java_25')) { $image = $candidate; break; }
        }
        if (!$image) { throw new RuntimeException('Paper egg has no Java 25 image; review before selecting another runtime'); }
        $server = app(App\Services\Servers\ServerCreationService::class)->handle([
            'name' => 'Fogata - Prueba', 'description' => 'New test world',
            'owner_id' => App\Models\User::where('username', 'admin')->firstOrFail()->id,
            'node_id' => $node->id, 'allocation_id' => $allocation->id, 'egg_id' => $egg->id,
            'memory' => 4096, 'swap' => 0, 'disk' => 20000, 'cpu' => 200, 'io' => 500,
            'environment' => $environment, 'image' => $image, 'backup_limit' => 1,
            'start_on_completion' => false,
        ]);
    }
    echo json_encode(['serverUuid' => $server->uuid, 'status' => $server->status]) . PHP_EOL;
} else { throw new RuntimeException('Unknown setup phase'); }
