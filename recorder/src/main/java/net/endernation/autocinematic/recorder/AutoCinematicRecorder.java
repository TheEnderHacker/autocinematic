package net.endernation.autocinematic.recorder;

import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.plugin.java.JavaPlugin;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;

/**
 * EnderNation AutoCinematic Recorder.
 *
 * Zeichnet Schuesse, Treffer, Kills und Projektil-Flugbahnen (SwornGuns) als JSONL auf,
 * damit sie spaeter ueber die Echtzeit-Uhr einer Flashback-Aufnahme tickgenau zugeordnet werden.
 *
 * Grundsaetze:
 *  - liest nur mit (MONITOR, ignoreCancelled), veraendert weder Waffen, Projektile, Schaden noch Gameplay;
 *  - keine harte Abhaengigkeit zu SwornGuns (Zugriff per Reflection, faellt sauber zurueck);
 *  - Daten bleiben lokal auf dem Server, Aufbewahrung begrenzt (retention-days), Befehle nur mit Permission.
 */
public final class AutoCinematicRecorder extends JavaPlugin {

    private EventWriter writer;
    private ProjectileTracker tracker;
    private volatile boolean recording;
    private final String sessionId = UUID.randomUUID().toString();

    @Override
    public void onEnable() {
        saveDefaultConfig();
        Path dir = getDataFolder().toPath().resolve(getConfig().getString("output-folder", "sessions"));
        try {
            writer = new EventWriter(dir, sessionId, getLogger());
            int removed = writer.deleteOlderThanDays(getConfig().getInt("retention-days", 7));
            if (removed > 0) getLogger().info("Aufbewahrung: " + removed + " alte Sitzungsdatei(en) entfernt");
        } catch (IOException e) {
            getLogger().severe("Ausgabeordner nicht nutzbar: " + e.getMessage() + " - Recorder bleibt aus");
            return;
        }
        recording = getConfig().getBoolean("enabled", true);
        SwornGunsBridge bridge = new SwornGunsBridge(getServer(), getLogger());
        tracker = new ProjectileTracker(this, writer, bridge,
                getConfig().getBoolean("track-projectiles", true),
                getConfig().getInt("max-projectile-ticks", 60));
        CombatListener listener = new CombatListener(this, writer, bridge, tracker);
        getServer().getPluginManager().registerEvents(listener, this);
        listener.registerSwornGunShotEvent();
        writer.writeSessionStart(getServer().getVersion(), getDescription().getVersion());
        getLogger().info("AutoCinematic Recorder aktiv (Aufnahme " + (recording ? "AN" : "AUS") + "), Sitzung " + sessionId
                + ", Ausgabe " + dir);
    }

    @Override
    public void onDisable() {
        if (tracker != null) tracker.flushAll();
        if (writer != null) writer.close();
    }

    public boolean isRecording() {
        return recording;
    }

    public String sessionId() {
        return sessionId;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!sender.hasPermission("autocinematic.admin")) {
            sender.sendMessage("Keine Berechtigung.");
            return true;
        }
        String sub = args.length > 0 ? args[0].toLowerCase() : "status";
        switch (sub) {
            case "on" -> {
                recording = true;
                sender.sendMessage("AutoCinematic: Aufnahme AN");
            }
            case "off" -> {
                recording = false;
                sender.sendMessage("AutoCinematic: Aufnahme AUS");
            }
            default -> sender.sendMessage("AutoCinematic: Aufnahme " + (recording ? "AN" : "AUS")
                    + " | Sitzung " + sessionId + " | geschrieben: " + (writer == null ? 0 : writer.written())
                    + " | SwornGuns erkannt: " + (tracker != null && tracker.bridgeAvailable()));
        }
        return true;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        return args.length == 1 ? List.of("on", "off", "status") : List.of();
    }
}
