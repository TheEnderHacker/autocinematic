package net.endernation.autocinematic.recorder;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.entity.Projectile;
import org.bukkit.scheduler.BukkitRunnable;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Zeichnet die echte Flugbahn von Projektilen auf: eine Position pro Server-Tick, bis das
 * Projektil verschwindet oder `maxTicks` erreicht ist. Nur lesend (getLocation), keine Eingriffe.
 */
final class ProjectileTracker {

    private final AutoCinematicRecorder plugin;
    private final EventWriter writer;
    private final SwornGunsBridge bridge;
    private final boolean enabled;
    private final int maxTicks;
    private final Map<UUID, Track> active = new ConcurrentHashMap<>();

    private final class Track extends BukkitRunnable {
        final Projectile projectile;
        final Player shooter;
        final List<List<Number>> points = new ArrayList<>();
        SwornGunsBridge.BulletInfo info;
        int ticks;
        boolean finished;

        Track(Projectile projectile, Player shooter) {
            this.projectile = projectile;
            this.shooter = shooter;
            sample();
        }

        void sample() {
            Location l = projectile.getLocation();
            points.add(List.of(Bukkit.getCurrentTick(), Json.round(l.getX()), Json.round(l.getY()), Json.round(l.getZ())));
        }

        @Override
        public void run() {
            if (info == null) info = bridge.bullet(projectile).orElse(null);
            if (!projectile.isValid()) {
                finish("removed");
                return;
            }
            sample();
            if (++ticks >= maxTicks) finish("maxTicks");
        }

        synchronized void finish(String reason) {
            if (finished) return;
            finished = true;
            try {
                cancel();
            } catch (IllegalStateException ignored) {
                // war noch nicht geplant
            }
            active.remove(projectile.getUniqueId());
            Map<String, Object> e = Json.event("trajectory", plugin.sessionId());
            e.put("shooter", Json.player(shooter));
            if (info != null && info.weapon() != null) e.put("weapon", info.weapon());
            Location start = projectile.getLocation();
            e.put("dim", Json.dim(start));
            Map<String, Object> x = Json.extra(e);
            x.put("projectile", projectile.getUniqueId().toString());
            x.put("projectileType", projectile.getType().name());
            if (info != null) {
                if (info.shotId() != null) x.put("shotId", info.shotId());
                if (info.pelletIndex() != null) x.put("pellet", info.pelletIndex());
            }
            x.put("points", points);
            x.put("end", reason);
            writer.submit(e);
        }
    }

    ProjectileTracker(AutoCinematicRecorder plugin, EventWriter writer, SwornGunsBridge bridge, boolean enabled, int maxTicks) {
        this.plugin = plugin;
        this.writer = writer;
        this.bridge = bridge;
        this.enabled = enabled;
        this.maxTicks = Math.max(1, maxTicks);
    }

    void start(Projectile projectile, Player shooter) {
        if (!enabled || !plugin.isRecording()) return;
        Track t = new Track(projectile, shooter);
        active.put(projectile.getUniqueId(), t);
        t.runTaskTimer(plugin, 1L, 1L);
    }

    /** Liefert die bisher bekannte Schuss-Info (fuer Treffer, falls die Bridge direkt nichts findet). */
    SwornGunsBridge.BulletInfo info(UUID projectile) {
        Track t = active.get(projectile);
        return t == null ? null : t.info;
    }

    void flushAll() {
        for (Track t : List.copyOf(active.values())) t.finish("shutdown");
    }

    boolean bridgeAvailable() {
        return bridge.available();
    }
}
