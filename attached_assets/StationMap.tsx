import { useEffect, useRef, useMemo } from 'react';
import { MapContainer, TileLayer, LayerGroup, Circle } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { useQuery } from '@tanstack/react-query';
import StationMarker from './StationMarker';
import type { RadarStation, MetarStation } from '@/lib/stations';
import { calculateDistance } from '@/lib/stations';
import L from 'leaflet';

interface StationMapProps {
  onRadarSelect: (id: string) => void;
  onMetarSelect: (id: string) => void;
  stationType: 'all' | 'radar' | 'metar';
  showRadarMosaic?: boolean;
  selectedRadarId?: string;
}

const RADIUS_NM = 120; // 120 nautical mile radius
const NM_TO_METERS = 1852; // 1 nautical mile = 1852 meters

export default function StationMap({ 
  onRadarSelect, 
  onMetarSelect, 
  stationType,
  showRadarMosaic = true,
  selectedRadarId
}: StationMapProps) {
  const mapRef = useRef<L.Map>(null);

  const { data: radarStations = [] } = useQuery<RadarStation[]>({
    queryKey: ['/api/stations/radar'],
  });

  const { data: metarStations = [] } = useQuery<MetarStation[]>({
    queryKey: ['/api/stations/metar'],
  });

  useEffect(() => {
    // Fix Leaflet default icon paths
    L.Icon.Default.imagePath = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/";
  }, []);

  const selectedRadar = useMemo(() => {
    return selectedRadarId ? radarStations.find(station => station.id === selectedRadarId) : null;
  }, [selectedRadarId, radarStations]);

  // Filter METAR stations based on selected radar
  const visibleMetarStations = useMemo(() => {
    if (!selectedRadar || stationType === 'radar') {
      return [];
    }

    return metarStations.filter(metar => {
      const distance = calculateDistance(
        selectedRadar.lat,
        selectedRadar.lon,
        metar.lat,
        metar.lon
      );
      return distance <= RADIUS_NM;
    });
  }, [selectedRadar, metarStations, stationType]);

  const shouldShowRadar = stationType === 'all' || stationType === 'radar';
  const shouldShowMetar = (stationType === 'all' || stationType === 'metar') && selectedRadar;

  return (
    <MapContainer
      center={[39.8283, -98.5795]}
      zoom={4}
      style={{ height: '600px', width: '100%' }}
      ref={mapRef}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {showRadarMosaic && (
        <TileLayer
          url="https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://mesonet.agron.iastate.edu/">IEM</a> NEXRAD'
          opacity={0.7}
        />
      )}

      <LayerGroup>
        {shouldShowRadar && radarStations.map((station) => (
          <StationMarker
            key={station.id}
            position={[station.lat, station.lon]}
            type="radar"
            id={station.id}
            onClick={() => onRadarSelect(station.id)}
          />
        ))}

        {selectedRadar && (
          <Circle
            center={[selectedRadar.lat, selectedRadar.lon]}
            radius={RADIUS_NM * NM_TO_METERS}
            pathOptions={{ color: 'blue', fillColor: 'blue', fillOpacity: 0.1 }}
          />
        )}

        {shouldShowMetar && visibleMetarStations.map((station) => (
          <StationMarker
            key={station.id}
            position={[station.lat, station.lon]}
            type="metar"
            id={station.id}
            onClick={() => onMetarSelect(station.id)}
          />
        ))}
      </LayerGroup>
    </MapContainer>
  );
}