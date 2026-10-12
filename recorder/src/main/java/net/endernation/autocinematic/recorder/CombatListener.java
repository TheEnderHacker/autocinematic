package net.endernation.autocinematic.recorder;

import org.bukkit.Location;
import org.bukkit.entity.LivingEntity;
import org.bukkit.entity.Player;
import org.bukkit.entity.Projectile;
import org.bukkit.event.Event;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.entity.PlayerDeathEvent;
import org.bukkit.event.entity.ProjectileLaunchEvent;
import org.bukkit.plugin.EventExecutor;
import org.bukkit.plugin.Plugin;

import java.lang.reflect.Method;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Nur lesende Listener (Prioritaet MONITOR, abgebrochene Ereignisse werden ignoriert).
 * Kein Listener veraendert Schaden, Projektile oder sonstigen Spielzustand.
 */
final class CombatListener implements Listener {

    private static final long KILL_ATTRIBUTION_MS = 4000;
    private static final double HEADSHOT_TOLERANCE = 0.26; // wie SwornGuns EntityListener

    private record LastHit(Player shooter, String weapon, Long shotId, long time, double distance, boolean headshot,
                           Location shooterPos) {}

    private final AutoCinematicRecorder plugin;
    private final EventWriter writer;
    private final SwornGunsBridge bridge;
    private final ProjectileTracker tracker;
    private final Map<UUID, LastHit> lastHit = new ConcurrentHashMap<>();

    CombatListener(AutoCinematicRecorder plugin, EventWriter writer, SwornGunsBridge bridge, ProjectileTracker tracker) {
        this.plugin = plugin;
        this.writer = writer;
        this.bridge = bridge;
        this.tracker = tracker;
    }

    // ------------------------------------------------------------------ Schuesse (SwornGuns)
    /** Registriert SwornGunShotEvent (ai-dev: mit shotId) bzw. SwornGunFireEvent, ohne Compile-Abhaengigkeit. */
    void registerSwornGunShotEvent() {
        Plugin sg = plugin.getServer().getPluginManager().getPlugin("SwornGuns");
        if (sg == null) return;
        ClassLoader cl = sg.getClass().getClassLoader();
        for (String name : new String[]{"net.dmulloy2.swornguns.events.SwornGunShotEvent",
                                        "net.dmulloy2.swornguns.events.SwornGunFireEvent"}) {
            try {
                Class<?> raw = Class.forName(name, true, cl);
                if (!Event.class.isAssignableFrom(raw)) continue;
                @SuppressWarnings("unchecked")
                Class<? extends Event> type = (Class<? extends Event>) raw;
                boolean withId = name.endsWith("ShotEvent");
                EventExecutor exec = (listener, event) -> {
                    if (type.isInstance(event)) onSwornShot(event, withId);
                };
                plugin.getServer().getPluginManager().registerEvent(type, this, EventPriority.MONITOR, exec, plugin, true);
                plugin.getLogger().info("Lausche auf " + raw.getSimpleName());
                return;
            } catch (ClassNotFoundException ignored) {
                // naechste Variante probieren
            }
        }
        plugin.getLogger().warning("Kein SwornGuns-Schussereignis gefunden - Schuesse werden nur ueber Projektile erkannt");
    }

    private void onSwornShot(Event event, boolean withId) {
        if (!plugin.isRecording()) return;
        Player p = (Player) invoke(event, "getPlayer");
        if (p == null) return;
        Map<String, Object> e = Json.event("shot", plugin.sessionId());
        e.put("shooter", Json.player(p));
        Object weapon = withId ? invoke(event, "getWeaponId") : invoke(invoke(event, "getGun"), "getName");
        if (weapon != null) e.put("weapon", weapon.toString());
        e.put("pos", Json.vec(p.getLocation()));
        e.put("dim", Json.dim(p.getLocation()));
        if (withId) {
            Object id = invoke(event, "getShotId");
            if (id != null) Json.extra(e).put("shotId", id);
        }
        writer.submit(e);
    }

    private static Object invoke(Object target, String method) {
        if (target == null) return null;
        try {
            Method m = target.getClass().getMethod(method);
            return m.invoke(target);
        } catch (ReflectiveOperationException | RuntimeException ex) {
            return null;
        }
    }

    // ------------------------------------------------------------------ Projektile
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onLaunch(ProjectileLaunchEvent event) {
        Projectile proj = event.getEntity();
        if (proj.getShooter() instanceof Player shooter) tracker.start(proj, shooter);
    }

    // ------------------------------------------------------------------ Treffer
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onDamage(EntityDamageByEntityEvent event) {
        if (!plugin.isRecording()) return;
        if (!(event.getDamager() instanceof Projectile proj) || !(proj.getShooter() instanceof Player shooter)) return;
        if (!(event.getEntity() instanceof LivingEntity victim)) return;

        SwornGunsBridge.BulletInfo info = bridge.bullet(proj).orElseGet(() -> tracker.info(proj.getUniqueId()));
        Location shooterPos = shooter.getLocation();
        Location victimPos = victim.getLocation();
        double distance = shooterPos.getWorld() == victimPos.getWorld() ? shooterPos.distance(victimPos) : -1;
        boolean headshot = Math.abs(proj.getLocation().getY() - victim.getEyeLocation().getY()) <= HEADSHOT_TOLERANCE;

        Map<String, Object> e = Json.event("hit", plugin.sessionId());
        e.put("shooter", Json.player(shooter));
        e.put("target", Json.player(victim));
        if (info != null && info.weapon() != null) e.put("weapon", info.weapon());
        if (distance >= 0) e.put("distance", Json.round(distance));
        if (headshot) e.put("headshot", true);
        e.put("damage", Json.round(event.getFinalDamage()));
        if (victim.getHealth() - event.getFinalDamage() <= 0) e.put("lethal", true);
        e.put("pos", Json.vec(shooterPos));
        e.put("targetPos", Json.vec(victimPos));
        e.put("dim", Json.dim(victimPos));
        Map<String, Object> x = Json.extra(e);
        x.put("projectile", proj.getUniqueId().toString());
        x.put("impact", Json.vec(proj.getLocation()));
        if (info != null) {
            if (info.shotId() != null) x.put("shotId", info.shotId());
            if (info.pelletIndex() != null) x.put("pellet", info.pelletIndex());
        }
        x.put("targetIsPlayer", victim instanceof Player);
        writer.submit(e);

        lastHit.put(victim.getUniqueId(), new LastHit(shooter, info == null ? null : info.weapon(),
                info == null ? null : info.shotId(), System.currentTimeMillis(), distance, headshot, shooterPos));
    }

    // ------------------------------------------------------------------ Kills
    @EventHandler(priority = EventPriority.MONITOR)
    public void onDeath(PlayerDeathEvent event) {
        if (!plugin.isRecording()) return;
        Player victim = event.getEntity();
        LastHit hit = lastHit.remove(victim.getUniqueId());
        boolean recent = hit != null && System.currentTimeMillis() - hit.time() <= KILL_ATTRIBUTION_MS;
        Player killer = victim.getKiller();
        if (killer == null && recent) killer = hit.shooter();
        if (killer == null) return; // kein Kampf-Tod (Fall, Lava ...) -> nicht relevant

        Map<String, Object> e = Json.event("kill", plugin.sessionId());
        e.put("shooter", Json.player(killer));
        e.put("target", Json.player(victim));
        if (recent && hit.weapon() != null) e.put("weapon", hit.weapon());
        if (recent && hit.distance() >= 0) e.put("distance", Json.round(hit.distance()));
        if (recent && hit.headshot()) e.put("headshot", true);
        e.put("pos", Json.vec(recent ? hit.shooterPos() : killer.getLocation()));
        e.put("targetPos", Json.vec(victim.getLocation()));
        e.put("dim", Json.dim(victim.getLocation()));
        if (recent && hit.shotId() != null) Json.extra(e).put("shotId", hit.shotId());
        Json.extra(e).put("attribution", recent ? "letzter Treffer <= 4 s" : "Bukkit getKiller");
        writer.submit(e);
    }
}
