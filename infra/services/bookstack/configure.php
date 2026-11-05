<?php
/** Entrada fija del bundle: datos por stdin, nunca PHP/código del solicitante. */
declare(strict_types=1);

use BookStack\Users\Models\User;
use BookStack\Users\UserRepo;
use BookStack\Settings\SettingService;
use Illuminate\Contracts\Console\Kernel;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

try {
    $raw = stream_get_contents(STDIN, 16385);
    if (strlen($raw) > 16384) {
        throw new RuntimeException();
    }
    $data = json_decode($raw, true, 16, JSON_THROW_ON_ERROR);
    if (!in_array($data['action'] ?? null, ['initialize', 'check'], true)) {
        throw new RuntimeException();
    }
    chdir('/var/www/bookstack');
    require '/var/www/bookstack/vendor/autoload.php';
    $app = require '/var/www/bookstack/bootstrap/app.php';
    $app->make(Kernel::class)->bootstrap();
    $identity = $data['resource_uuid'];
    $keyHash = hash('sha256', (string) config('app.key'));
    if ($data['action'] === 'initialize') {
        if (!Schema::hasTable('nap_bootstrap')) {
            Schema::create('nap_bootstrap', static function (Blueprint $table): void {
                $table->unsignedInteger('id')->primary();
                $table->string('resource_uuid', 36);
                $table->string('key_hash', 64);
                $table->unsignedInteger('teacher_id');
            });
        }
        DB::transaction(static function () use ($data, $identity, $keyHash): void {
            $marker = DB::table('nap_bootstrap')->where('id', 1)->lockForUpdate()->first();
            if ($marker !== null) {
                if ($marker->resource_uuid !== $identity || $marker->key_hash !== $keyHash) {
                    throw new RuntimeException();
                }
                // Ni un corte después del COMMIT autoriza cambiar contraseñas.
                return;
            }
            if ($data['teacher_email'] === 'admin@admin.com' || !filter_var($data['teacher_email'], FILTER_VALIDATE_EMAIL)) {
                throw new RuntimeException();
            }
            $initial = User::query()->where('email', 'admin@admin.com')->first();
            if (!$initial || !$initial->hasSystemRole('admin')
                || User::query()->where('email', $data['teacher_email'])->exists()) {
                throw new RuntimeException();
            }
            // API de la versión fijada: mantiene hash/slug y admite nombres de
            // un carácter según el contrato, sin poner la contraseña en argv.
            $teacher = app(UserRepo::class)->updateWithoutActivity($initial, [
                'email' => $data['teacher_email'], 'name' => $data['teacher_name'],
                'password' => $data['teacher_password'], 'language' => $data['locale'],
            ], true);
            $teacher->email_confirmed = true;
            $teacher->save();
            $settings = app(SettingService::class);
            $settings->put('app-public', 'false');
            $settings->put('registration-enabled', 'false');
            $settings->put('app-name', $data['display_name']);
            DB::table('nap_bootstrap')->insert([
                'id' => 1, 'resource_uuid' => $identity, 'key_hash' => $keyHash, 'teacher_id' => $teacher->id,
            ]);
        });
    }
    $marker = DB::table('nap_bootstrap')->where('id', 1)->first();
    $teacher = $marker ? User::query()->find($marker->teacher_id) : null;
    $settings = app(SettingService::class);
    if (!$marker || $marker->resource_uuid !== $identity || $marker->key_hash !== $keyHash
        || !$teacher || !$teacher->hasSystemRole('admin')
        || User::query()->where('email', 'admin@admin.com')->exists()
        || $settings->get('app-public') !== false || $settings->get('registration-enabled') !== false
        || config('filesystems.default') !== 'local_secure'
        || config('filesystems.images') !== 'local_secure'
        || config('filesystems.attachments') !== 'local_secure') {
        throw new RuntimeException();
    }
    echo '{"ready":true}', PHP_EOL;
} catch (Throwable $error) {
    // No reportar excepción, SQL, salida de Artisan, secretos ni trazas.
    fwrite(STDERR, "BOOKSTACK_PREPARATION_UNCONFIRMED\n");
    exit(1);
}
