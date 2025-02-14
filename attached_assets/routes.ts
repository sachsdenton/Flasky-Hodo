import type { Express } from "express";
import { createServer, type Server } from "http";
import fs from "fs";
import path from "path";
import fetch from "node-fetch";
import * as xml2js from "xml2js";

interface MetarStation {
  id: string;
  name: string;
  state: string;
  lat: number;  
  lon: number;  
}

interface RadarStation {
  id: string;
  lat: number;
  lon: number;
  radarType: string;
}

async function fetchMetarStationCoords(): Promise<Record<string, [number, number]>> {
  try {
    const response = await fetch('https://forecast.weather.gov/xml/index.xml');
    const xmlData = await response.text();
    const parser = new xml2js.Parser();
    const result = await parser.parseStringPromise(xmlData);

    const coordMap: Record<string, [number, number]> = {};
    const stations = result.wx_station_index.station || [];

    stations.forEach((station: any) => {
      const id = station.station_id?.[0];
      const lat = parseFloat(station.latitude?.[0]);
      const lon = parseFloat(station.longitude?.[0]);

      if (id && !isNaN(lat) && !isNaN(lon)) {
        coordMap[id] = [lat, lon];
      }
    });

    return coordMap;
  } catch (error) {
    console.error('Error fetching station coordinates:', error);
    return {};
  }
}

async function fetchRadarStations(): Promise<RadarStation[]> {
  try {
    console.log('Fetching radar stations from WFS...');
    const response = await fetch('https://opengeo.ncep.noaa.gov/geoserver/nws/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=nws:radar_sites');
    const xmlData = await response.text();
    console.log('Received XML data length:', xmlData.length);

    const parser = new xml2js.Parser();
    const result = await parser.parseStringPromise(xmlData);

    // Debug the structure
    const features = result['wfs:FeatureCollection']?.['gml:featureMember'] || [];
    console.log('Number of features found:', features.length);

    if (features.length > 0) {
      console.log('Sample feature structure:', JSON.stringify(features[0], null, 2));
    }

    const stations: RadarStation[] = [];

    features.forEach((feature: any) => {
      const radarSite = feature['nws:radar_sites']?.[0];
      if (radarSite) {
        // Extract and log each field for debugging
        const id = radarSite['nws:rda_id']?.[0];  
        const lat = parseFloat(radarSite['nws:lat']?.[0]);
        const lon = parseFloat(radarSite['nws:lon']?.[0]);
        const type = radarSite['nws:rpg_id_dec']?.[0] ? 'NEXRAD' : 'TDWR';  

        console.log('Processing station:', { id, lat, lon, type });

        if (id && !isNaN(lat) && !isNaN(lon)) {
          stations.push({
            id,
            lat,
            lon,
            radarType: type
          });
        }
      }
    });

    console.log(`Found ${stations.length} valid radar stations`);
    return stations;
  } catch (error) {
    console.error('Error fetching radar stations:', error);
    return [];
  }
}

export async function registerRoutes(app: Express): Promise<Server> {
  // Fetch initial data
  console.log('Starting to fetch radar stations...');
  const radarStations = await fetchRadarStations();
  console.log(`Loaded ${radarStations.length} radar stations`);
  const metarCoords = await fetchMetarStationCoords();

  // Read and parse METAR stations from CSV
  const metarStations: MetarStation[] = [];
  const csvPath = path.join(process.cwd(), "attached_assets", "METAR Sites US.csv");
  const csvContent = fs.readFileSync(csvPath, 'utf-8');

  // Skip header row and process each line
  const lines = csvContent.split('\n').slice(1);
  lines.forEach(line => {
    if (line.trim()) {
      const [state, name, id] = line.split(',');
      if (state && name && id) {
        const trimmedId = id.trim();
        // Check if we have coordinates for this station from XML
        const coords = metarCoords[trimmedId];
        if (coords) {
          metarStations.push({
            state: state.trim(),
            name: name.trim(),
            id: trimmedId,
            lat: coords[0],
            lon: coords[1]
          });
        }
      }
    }
  });

  app.get("/api/stations/radar", (_req, res) => {
    res.json(radarStations);
  });

  app.get("/api/stations/metar", (_req, res) => {
    res.json(metarStations);
  });

  app.get("/api/stations/radar/:id", (req, res) => {
    const station = radarStations.find(s => s.id === req.params.id);
    if (!station) {
      res.status(404).json({ message: "Station not found" });
      return;
    }
    res.json(station);
  });

  app.get("/api/stations/metar/:id", (req, res) => {
    const station = metarStations.find(s => s.id === req.params.id);
    if (!station) {
      res.status(404).json({ message: "Station not found" });
      return;
    }
    res.json(station);
  });

  const httpServer = createServer(app);
  return httpServer;
}