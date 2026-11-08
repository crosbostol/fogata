<?php
// CLI-only registration of an additional Forge server. Existing worlds are untouched.
if (PHP_SAPI !== 'cli') { exit(1); }
$input = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
chdir('/var/www/pelican');
require 'vendor/autoload.php';
$app = require 'bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$name = $input['name'];
$version = $input['forge'];
if (!preg_match('/^[0-9.]+-[0-9.]+$/', $version)) { throw new RuntimeException('Invalid Forge version'); }
$node = App\Models\Node::where('name', 'Fogata')->firstOrFail();
$egg = App\Models\Egg::where('name', 'Forge Minecraft')->first();
if (!$egg) {
    app(App\Services\Eggs\Sharing\EggImporterService::class)->fromUrl('https://raw.githubusercontent.com/pelican-eggs/minecraft/main/java/forge/egg-forge-minecraft.yaml');
    $egg = App\Models\Egg::where('name', 'Forge Minecraft')->firstOrFail();
}
$server = App\Models\Server::where('name', $name)->first();
if (!$server) {
    $allocation = App\Models\Allocation::firstOrCreate(['node_id'=>$node->id, 'ip'=>'0.0.0.0', 'port'=>$input['port']]);
    if ($allocation->server_id) { throw new RuntimeException('Port already assigned'); }
    $env = [];
    foreach ($egg->variables as $v) { $env[$v->env_variable] = $v->default_value; }
    $env['MC_VERSION'] = explode('-', $version)[0];
    $env['FORGE_VERSION'] = $version;
    $image = null;
    foreach ($egg->docker_images as $candidate) { if (str_contains($candidate, 'java_17')) { $image=$candidate; break; } }
    if (!$image) { throw new RuntimeException('Java 17 image missing'); }
    $server = app(App\Services\Servers\ServerCreationService::class)->handle([
        'name'=>$name, 'description'=>'Exclusive Fogata modpack server',
        'owner_id'=>App\Models\User::where('username','admin')->firstOrFail()->id,
        'node_id'=>$node->id, 'allocation_id'=>$allocation->id, 'egg_id'=>$egg->id,
        'memory'=>6144,'swap'=>0,'disk'=>20000,'cpu'=>200,'io'=>500,
        'environment'=>$env,'image'=>$image,'backup_limit'=>1,'start_on_completion'=>false,
    ]);
}
echo json_encode(['uuid'=>$server->uuid,'status'=>$server->status,'image'=>$server->image]);
