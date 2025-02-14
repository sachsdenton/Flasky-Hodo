import { Marker, Popup } from 'react-leaflet';
import L from 'leaflet';

interface StationMarkerProps {
  position: [number, number];
  type: 'radar' | 'metar';
  id: string;
  onClick: () => void;
}

export default function StationMarker({ position, type, id, onClick }: StationMarkerProps) {
  const size = type === 'radar' ? 12 : 8;
  const icon = L.divIcon({
    className: 'custom-div-icon',
    html: `<div style="
      width: ${size}px; 
      height: ${size}px; 
      background: ${type === 'radar' ? '#ef4444' : '#3b82f6'}; 
      border: 2px solid white;
      ${type === 'radar' ? 'transform: rotate(45deg)' : 'border-radius: 50%'};
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size/2, size/2]
  });

  return (
    <Marker 
      position={position} 
      icon={icon}
      eventHandlers={{
        click: onClick
      }}
    >
      <Popup>
        <div className="text-sm font-medium">
          Station ID: {id}
          <br/>
          Type: {type.toUpperCase()}
        </div>
      </Popup>
    </Marker>
  );
}