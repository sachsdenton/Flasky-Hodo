import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { useQuery } from "@tanstack/react-query";
import type { RadarStation, MetarStation } from '@/lib/stations';

interface InfoBoxProps {
  title: string;
  stationId: string;
  type: 'radar' | 'metar';
}

export default function InfoBox({ title, stationId, type }: InfoBoxProps) {
  const { data: stationInfo } = useQuery<RadarStation | MetarStation>({
    queryKey: [`/api/stations/${type}/${stationId}`],
    enabled: !!stationId
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {stationId ? (
          <div className="space-y-2">
            <p className="text-2xl font-bold">{stationId}</p>
            {stationInfo && (
              <>
                <p>Latitude: {stationInfo.lat.toFixed(2)}°</p>
                <p>Longitude: {stationInfo.lon.toFixed(2)}°</p>
                {'radarType' in stationInfo && (
                  <p>Type: {stationInfo.radarType}</p>
                )}
                {'elevation' in stationInfo && (
                  <p>Elevation: {stationInfo.elevation} ft</p>
                )}
              </>
            )}
          </div>
        ) : (
          <p className="text-muted-foreground">Select a {type} station on the map</p>
        )}
      </CardContent>
    </Card>
  );
}