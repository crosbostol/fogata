<?php
// Run after stopping all listed containers. Shared flock prevents concurrent JVMs.
if (PHP_SAPI !== 'cli') { exit(1); }
$input=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
chdir('/var/www/pelican'); require 'vendor/autoload.php';
$app=require 'bootstrap/app.php'; $app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$mount=App\Models\Mount::firstOrCreate(['name'=>'Fogata exclusive session'],[
    'uuid'=>(string)Illuminate\Support\Str::uuid(), 'description'=>'One Minecraft JVM per VM',
    'source'=>'/var/lib/fogata/exclusive','target'=>'/mnt/fogata','read_only'=>false,'user_mountable'=>false,
]);
foreach ($input as $uuid) {
    $s=App\Models\Server::where('uuid',$uuid)->firstOrFail();
    $mount->nodes()->syncWithoutDetaching([$s->node_id]);
    $mount->eggs()->syncWithoutDetaching([$s->egg_id]);
    $s->mounts()->syncWithoutDetaching([$mount->id]);
    if ($s->egg->name === 'Forge Minecraft') {
        $s->startup = 'java @user_jvm_args.txt @unix_args.txt nogui';
    }
    if (!str_starts_with($s->startup,'flock -n /mnt/fogata/active.lock ')) {
        $s->startup='flock -n /mnt/fogata/active.lock '.$s->startup;
        $s->saveOrFail();
    }
    app(App\Repositories\Daemon\DaemonServerRepository::class)->setServer($s)->sync();
}
echo "Exclusive startup configured.\n";
