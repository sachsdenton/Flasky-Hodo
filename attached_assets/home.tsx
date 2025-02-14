import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import StationMap from "@/components/map/StationMap";
import InfoBox from "@/components/map/InfoBox";
import { useState } from "react";

type StationType = 'all' | 'radar' | 'metar';

export default function Home() {
  const [selectedRadar, setSelectedRadar] = useState<string>("");
  const [selectedMetar, setSelectedMetar] = useState<string>("");
  const [stationType, setStationType] = useState<StationType>('all');

  const handleRadarSelect = (id: string) => {
    setSelectedRadar(id);
    // Clear METAR selection when new radar is selected
    setSelectedMetar("");
  };

  return (
    <div className="min-h-screen bg-background p-4">
      <div className="container mx-auto space-y-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <h1 className="text-3xl font-bold">US Weather Station Map</h1>
          <div className="flex gap-2">
            <Button
              variant={stationType === 'all' ? 'default' : 'outline'}
              onClick={() => setStationType('all')}
            >
              All Stations
            </Button>
            <Button
              variant={stationType === 'radar' ? 'default' : 'outline'}
              onClick={() => setStationType('radar')}
            >
              RADAR Only
            </Button>
            <Button
              variant={stationType === 'metar' ? 'default' : 'outline'}
              onClick={() => setStationType('metar')}
            >
              METAR Only
            </Button>
          </div>
        </div>

        <Card className="p-1">
          <StationMap 
            onRadarSelect={handleRadarSelect}
            onMetarSelect={setSelectedMetar}
            stationType={stationType}
            selectedRadarId={selectedRadar}
          />
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <InfoBox 
            title="Radar Station" 
            stationId={selectedRadar} 
            type="radar"
          />
          <InfoBox 
            title="METAR Station" 
            stationId={selectedMetar}
            type="metar"
          />
        </div>
      </div>
    </div>
  );
}