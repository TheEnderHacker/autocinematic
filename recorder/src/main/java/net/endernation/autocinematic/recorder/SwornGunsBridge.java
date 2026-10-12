package net.endernation.autocinematic.recorder;

import org.bukkit.Server;
import org.bukkit.entity.Entity;
import org.bukkit.plugin.Plugin;

import java.lang.reflect.Method;
import java.util.Optional;
import java.util.logging.Logger;

/**
 * Lesender Zugriff auf SwornGuns ohne Compile-Abhaengigkeit.
 * Nutzt: SwornGuns#getBullet(Entity) -> Bullet#getShotId/getPelletIndex/getShotFrom -> Gun#getName.
 * Fehlt etwas (andere Version), werden die Zusatzfelder einfach weggelassen.
 */
final class SwornGunsBridge {

    record BulletInfo(Long shotId, Integer pelletIndex, String weapon) {}

    private final Plugin swornGuns;
    private final Method getBullet;
    private final Logger log;
    private boolean warned;

    SwornGunsBridge(Server server, Logger log) {
        this.log = log;
        Plugin p = server.getPluginManager().getPlugin("SwornGuns");
        Method m = null;
        if (p != null) {
            try {
                m = p.getClass().getMethod("getBullet", Entity.class);
            } catch (NoSuchMethodException e) {
                log.warning("SwornGuns gefunden, aber getBullet(Entity) fehlt - Schuss-IDs werden nicht erfasst");
            }
        } else {
            log.info("SwornGuns nicht installiert - erfasst werden nur allgemeine Projektil-/Schadensereignisse");
        }
        this.swornGuns = p;
        this.getBullet = m;
    }

    boolean available() {
        return swornGuns != null && getBullet != null && swornGuns.isEnabled();
    }

    Optional<BulletInfo> bullet(Entity projectile) {
        if (!available()) return Optional.empty();
        try {
            Object bullet = getBullet.invoke(swornGuns, projectile);
            if (bullet == null) return Optional.empty();
            Long shotId = call(bullet, "getShotId", Long.class);
            Integer pellet = call(bullet, "getPelletIndex", Integer.class);
            String weapon = null;
            Object gun = call(bullet, "getShotFrom", Object.class);
            if (gun != null) {
                weapon = call(gun, "getName", String.class);
                if (weapon == null) weapon = call(gun, "getGunName", String.class);
            }
            return Optional.of(new BulletInfo(shotId, pellet, weapon));
        } catch (ReflectiveOperationException | RuntimeException e) {
            if (!warned) {
                warned = true;
                log.warning("SwornGuns-Abfrage fehlgeschlagen (" + e.getClass().getSimpleName() + ") - Zusatzdaten werden ausgelassen");
            }
            return Optional.empty();
        }
    }

    private static <T> T call(Object target, String name, Class<T> type) {
        try {
            Method m = target.getClass().getMethod(name);
            Object v = m.invoke(target);
            if (v == null) return null;
            if (type == Long.class && v instanceof Number n) return type.cast(n.longValue());
            if (type == Integer.class && v instanceof Number n) return type.cast(n.intValue());
            return type.isInstance(v) ? type.cast(v) : null;
        } catch (ReflectiveOperationException | RuntimeException e) {
            return null;
        }
    }
}
