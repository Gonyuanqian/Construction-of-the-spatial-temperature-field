package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.zip.GZIPOutputStream;
import org.junit.jupiter.api.Test;

class QWeatherHttpTransportTest {
    @Test void sendsKeyOnlyInHeaderHandlesGzipAndDoesNotFollowRedirects() throws Exception {
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);var redirected=new AtomicInteger();
        var bytes=new ByteArrayOutputStream();try(var gzip=new GZIPOutputStream(bytes)){gzip.write("{\"forecasts\":[]}".getBytes(StandardCharsets.UTF_8));}
        server.createContext("/gzip",exchange->{assertEquals("test-key",exchange.getRequestHeaders().getFirst("X-QW-Api-Key"));assertNull(exchange.getRequestURI().getQuery());exchange.getResponseHeaders().add("Content-Encoding","gzip");exchange.sendResponseHeaders(200,bytes.size());exchange.getResponseBody().write(bytes.toByteArray());exchange.close();});
        server.createContext("/redirect",exchange->{exchange.getResponseHeaders().add("Location","/target");exchange.sendResponseHeaders(302,-1);exchange.close();});
        server.createContext("/target",exchange->{redirected.incrementAndGet();exchange.sendResponseHeaders(200,-1);exchange.close();});
        server.start();
        try {
            String base="http://127.0.0.1:"+server.getAddress().getPort();var transport=new QWeatherClient.HttpTransport();
            assertEquals("{\"forecasts\":[]}",transport.get(URI.create(base+"/gzip"),"test-key").body());
            assertEquals(302,transport.get(URI.create(base+"/redirect"),"test-key").status());assertEquals(0,redirected.get());
        }finally{server.stop(0);}
    }
}
