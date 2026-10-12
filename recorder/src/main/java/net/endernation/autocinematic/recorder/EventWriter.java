package net.endernation.autocinematic.recorder;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.logging.Logger;

/** Schreibt Ereignisse asynchron als JSON-Zeilen (eine Datei pro Server-Sitzung). */
final class EventWriter {

    static final String PREFIX = "ac-";
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneOffset.UTC);

    private final Gson gson = new GsonBuilder().disableHtmlEscaping().create();
    private final ExecutorService disk = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "AutoCinematic-Writer");
        t.setDaemon(true);
        return t;
    });
    private final Path dir;
    private final Path file;
    private final String sessionId;
    private final Logger log;
    private final AtomicLong written = new AtomicLong();
    private BufferedWriter out;

    EventWriter(Path dir, String sessionId, Logger log) throws IOException {
        this.dir = dir;
        this.sessionId = sessionId;
        this.log = log;
        Files.createDirectories(dir);
        this.file = dir.resolve(PREFIX + FILE_TIME.format(Instant.now()) + "-" + sessionId.substring(0, 8) + ".jsonl");
    }

    /** Loescht nur eigene Sitzungsdateien (ac-*.jsonl) in diesem Ordner, die aelter als `days` sind. */
    int deleteOlderThanDays(int days) {
        if (days <= 0) return 0;
        Instant limit = Instant.now().minus(days, ChronoUnit.DAYS);
        int n = 0;
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir, PREFIX + "*.jsonl")) {
            for (Path p : ds) {
                if (Files.getLastModifiedTime(p).toInstant().isBefore(limit)) {
                    Files.deleteIfExists(p);
                    n++;
                }
            }
        } catch (IOException e) {
            log.warning("Aufbewahrung konnte nicht geprueft werden: " + e.getMessage());
        }
        return n;
    }

    void writeSessionStart(String serverVersion, String pluginVersion) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("v", 1);
        m.put("type", "session");
        m.put("t", System.currentTimeMillis());
        m.put("extra", Map.of("session", sessionId, "server", serverVersion, "plugin", pluginVersion));
        submit(m);
    }

    /** Thread-sicher; die eigentliche Datei-Arbeit laeuft im Writer-Thread. */
    void submit(Map<String, Object> event) {
        final String line = gson.toJson(event);
        disk.execute(() -> {
            try {
                if (out == null) {
                    out = Files.newBufferedWriter(file, StandardCharsets.UTF_8,
                            StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                }
                out.write(line);
                out.write('\n');
                out.flush();
                written.incrementAndGet();
            } catch (IOException e) {
                log.warning("Schreiben fehlgeschlagen: " + e.getMessage());
            }
        });
    }

    long written() {
        return written.get();
    }

    Path file() {
        return file;
    }

    void close() {
        disk.execute(() -> {
            try {
                if (out != null) out.close();
            } catch (IOException ignored) {
            }
        });
        disk.shutdown();
        try {
            disk.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
