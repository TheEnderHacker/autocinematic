package net.endernation.autocinematic.recorder;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.entity.Entity;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Bausteine fuer Ereignisse im AutoCinematic-Schema v1. */
final class Json {

    private Json() {}

    static Map<String, Object> event(String type, String session) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("v", 1);
        m.put("type", type);
        m.put("t", System.currentTimeMillis());
        Map<String, Object> extra = new LinkedHashMap<>();
        extra.put("serverTick", Bukkit.getCurrentTick());
        extra.put("session", session);
        m.put("extra", extra);
        return m;
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> extra(Map<String, Object> event) {
        return (Map<String, Object>) event.get("extra");
    }

    static Map<String, Object> player(Entity e) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("name", e.getName());
        m.put("uuid", e.getUniqueId().toString());
        return m;
    }

    static List<Double> vec(Location l) {
        return List.of(round(l.getX()), round(l.getY()), round(l.getZ()));
    }

    static String dim(Location l) {
        return l.getWorld() == null ? null : l.getWorld().getKey().toString();
    }

    static double round(double d) {
        return Math.round(d * 100.0) / 100.0;
    }
}
