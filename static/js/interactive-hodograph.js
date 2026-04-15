class InteractiveHodograph {
    constructor(container) {
        this.container = container;
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.container.innerHTML = '';
        this.container.appendChild(this.canvas);

        this.data = null;
        this.stormMotion = null;
        this.metarData = null;
        this.metarStation = '';

        this.scale = 1.0;
        this.offsetX = 0;
        this.offsetY = 0;
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        this.dragOffsetX = 0;
        this.dragOffsetY = 0;

        this.features = {
            speedRings: true,
            heightMarkers: true,
            halfKmMarkers: true,
            srhShading: true,
            shearVector: true,
            criticalAngle: true,
            stormMotionMarker: true,
            surfaceWindMarker: true,
            paramText: true
        };

        this.hoveredPoint = null;
        this.dpr = window.devicePixelRatio || 1;

        this._setupCanvas();
        this._bindEvents();
    }

    _setupCanvas() {
        const rect = this.container.getBoundingClientRect();
        const w = rect.width || this.container.clientWidth || 500;
        const h = rect.height || this.container.clientHeight || 500;
        const size = Math.max(Math.min(w, h), 300);
        this.width = size;
        this.height = size;
        this.canvas.width = size * this.dpr;
        this.canvas.height = size * this.dpr;
        this.canvas.style.width = size + 'px';
        this.canvas.style.height = size + 'px';
        this.canvas.style.cursor = 'grab';
        this.ctx.scale(this.dpr, this.dpr);
    }

    _bindEvents() {
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
            const rect = this.canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            const wx = (mx - this.width / 2 - this.offsetX) / this.scale;
            const wy = (my - this.height / 2 - this.offsetY) / this.scale;

            this.scale *= zoomFactor;
            this.scale = Math.max(0.2, Math.min(10, this.scale));

            this.offsetX = mx - this.width / 2 - wx * this.scale;
            this.offsetY = my - this.height / 2 - wy * this.scale;

            this.render();
        });

        this.canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.dragStartX = e.clientX;
            this.dragStartY = e.clientY;
            this.dragOffsetX = this.offsetX;
            this.dragOffsetY = this.offsetY;
            this.canvas.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', (e) => {
            if (this.isDragging) {
                this.offsetX = this.dragOffsetX + (e.clientX - this.dragStartX);
                this.offsetY = this.dragOffsetY + (e.clientY - this.dragStartY);
                this.render();
            } else if (this.data) {
                const rect = this.canvas.getBoundingClientRect();
                const mx = e.clientX - rect.left;
                const my = e.clientY - rect.top;
                this._checkHover(mx, my);
            }
        });

        window.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.isDragging = false;
                this.canvas.style.cursor = 'grab';
            }
        });

        window.addEventListener('resize', () => {
            this._setupCanvas();
            if (this.data) this.render();
        });

        if (typeof ResizeObserver !== 'undefined') {
            this._resizeObserver = new ResizeObserver(() => {
                this._setupCanvas();
                if (this.data) this.render();
            });
            this._resizeObserver.observe(this.container);
        }
    }

    _toScreen(u, v) {
        const cx = this.width / 2 + this.offsetX;
        const cy = this.height / 2 + this.offsetY;
        const pxPerKt = (this.width / 2 - 40) / (this.data ? this._maxRange() : 60);
        const sx = cx + u * pxPerKt * this.scale;
        const sy = cy - v * pxPerKt * this.scale;
        return [sx, sy];
    }

    _maxRange() {
        if (!this.data) return 60;
        const ms = this.data.max_speed;
        return Math.ceil(ms / 10) * 10 + 10;
    }

    _checkHover(mx, my) {
        if (!this.data) return;
        let closest = null;
        let minDist = 15;
        for (let i = 0; i < this.data.u_components.length; i++) {
            const [sx, sy] = this._toScreen(this.data.u_components[i], this.data.v_components[i]);
            const dist = Math.sqrt((mx - sx) ** 2 + (my - sy) ** 2);
            if (dist < minDist) {
                minDist = dist;
                closest = i;
            }
        }
        if (closest !== this.hoveredPoint) {
            this.hoveredPoint = closest;
            this.canvas.style.cursor = closest !== null ? 'pointer' : 'grab';
            this.render();
        }
    }

    setData(data) {
        this.data = data;
        this.scale = 1.0;
        this.offsetX = 0;
        this.offsetY = 0;
        this.render();
    }

    setStormMotion(dir, spd) {
        if (dir !== null && spd !== null && !isNaN(dir) && !isNaN(spd)) {
            const rad = (270 - dir) * Math.PI / 180;
            this.stormMotion = { u: spd * Math.cos(rad), v: spd * Math.sin(rad), direction: dir, speed: spd };
        } else {
            this.stormMotion = null;
        }
    }

    setMetar(dir, spd, station) {
        if (dir !== null && spd !== null && !isNaN(dir) && !isNaN(spd)) {
            const rad = (270 - dir) * Math.PI / 180;
            this.metarData = { u: spd * Math.cos(rad), v: spd * Math.sin(rad), direction: dir, speed: spd };
            this.metarStation = station || '';
        } else {
            this.metarData = null;
        }
    }

    toggleFeature(name, enabled) {
        this.features[name] = enabled;
        this.render();
    }

    resetView() {
        this.scale = 1.0;
        this.offsetX = 0;
        this.offsetY = 0;
        this.render();
    }

    render() {
        if (!this.data) return;
        const ctx = this.ctx;
        const w = this.width;
        const h = this.height;

        ctx.clearRect(0, 0, w, h);

        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, w, h);

        this._drawGrid();
        if (this.features.speedRings) this._drawSpeedRings();
        this._drawAxes();

        if (this.features.srhShading && this.stormMotion && this.metarData) this._drawSRH();
        if (this.features.shearVector && this.stormMotion && this.metarData) this._drawShearVector();
        if (this.features.criticalAngle && this.stormMotion && this.metarData) this._drawCriticalAngle();

        this._drawProfile();
        if (this.features.heightMarkers) this._drawHeightMarkers();
        if (this.features.stormMotionMarker && this.stormMotion) this._drawStormMotion();
        if (this.features.surfaceWindMarker && this.metarData) this._drawSurfaceWind();
        if (this.features.paramText) this._drawParamText();

        this._drawTitle();

        if (this.hoveredPoint !== null) this._drawTooltip();

        this._drawZoomInfo();
    }

    _drawGrid() {
        const ctx = this.ctx;
        const [cx, cy] = this._toScreen(0, 0);
        ctx.strokeStyle = '#e0e0e0';
        ctx.lineWidth = 0.5;
        const maxR = this._maxRange();
        const pxPerKt = (this.width / 2 - 40) / maxR;

        for (let v = -maxR; v <= maxR; v += 10) {
            const [x1, y1] = this._toScreen(-maxR, v);
            const [x2, y2] = this._toScreen(maxR, v);
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }
        for (let u = -maxR; u <= maxR; u += 10) {
            const [x1, y1] = this._toScreen(u, -maxR);
            const [x2, y2] = this._toScreen(u, maxR);
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }
    }

    _drawSpeedRings() {
        const ctx = this.ctx;
        const [cx, cy] = this._toScreen(0, 0);
        const maxR = this._maxRange();
        const pxPerKt = (this.width / 2 - 40) / maxR;

        ctx.strokeStyle = '#aaaaaa';
        ctx.lineWidth = 0.8;
        ctx.setLineDash([5, 5]);
        for (let r = 10; r <= maxR; r += 10) {
            const radius = r * pxPerKt * this.scale;
            ctx.beginPath();
            ctx.arc(cx, cy, radius, 0, Math.PI * 2);
            ctx.stroke();

            ctx.setLineDash([]);
            ctx.fillStyle = '#888';
            ctx.font = '10px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(r + '', cx + radius + 2, cy - 3);
            ctx.setLineDash([5, 5]);
        }
        ctx.setLineDash([]);
    }

    _drawAxes() {
        const ctx = this.ctx;
        const [cx, cy] = this._toScreen(0, 0);
        const maxR = this._maxRange();
        const pxPerKt = (this.width / 2 - 40) / maxR;
        const extent = maxR * pxPerKt * this.scale;

        ctx.strokeStyle = '#666';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(cx - extent, cy); ctx.lineTo(cx + extent, cy); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(cx, cy - extent); ctx.lineTo(cx, cy + extent); ctx.stroke();

        ctx.fillStyle = '#333';
        ctx.font = 'bold 13px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('N', cx, cy + extent + 16);
        ctx.fillText('S', cx, cy - extent - 8);
        ctx.fillText('E', cx - extent - 14, cy + 4);
        ctx.fillText('W', cx + extent + 14, cy + 4);
    }

    _drawProfile() {
        const ctx = this.ctx;
        const u = this.data.u_components;
        const v = this.data.v_components;
        const heights = this.data.heights;
        if (u.length < 2) return;

        const maxH = Math.max(...heights);

        for (let i = 0; i < u.length - 1; i++) {
            const [x1, y1] = this._toScreen(u[i], v[i]);
            const [x2, y2] = this._toScreen(u[i + 1], v[i + 1]);
            const t = heights[i] / (maxH || 1);
            ctx.strokeStyle = this._heightColor(t);
            ctx.lineWidth = 2.5;
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }

        for (let i = 0; i < u.length; i++) {
            const [sx, sy] = this._toScreen(u[i], v[i]);
            ctx.fillStyle = 'rgba(200, 50, 50, 0.5)';
            ctx.beginPath(); ctx.arc(sx, sy, 3, 0, Math.PI * 2); ctx.fill();
        }
    }

    _heightColor(t) {
        const r = Math.round(68 + (253 - 68) * t);
        const g = Math.round(1 + (231 - 1) * (1 - Math.abs(t - 0.5) * 2));
        const b = Math.round(84 + (37 - 84) * t);
        return `rgb(${r},${g},${b})`;
    }

    _drawHeightMarkers() {
        const ctx = this.ctx;
        const u = this.data.u_components;
        const v = this.data.v_components;
        const heights = this.data.heights;

        const maxHm = Math.max(...heights) * 1000;
        const targets = [];
        for (let km = 0.5; km <= maxHm / 1000 + 0.5; km += 0.5) {
            targets.push(km);
        }

        for (const targetKm of targets) {
            const targetM = targetKm * 1000;
            let closestIdx = -1;
            let minDiff = Infinity;
            for (let i = 0; i < heights.length; i++) {
                const diff = Math.abs(heights[i] * 1000 - targetM);
                if (diff < minDiff) { minDiff = diff; closestIdx = i; }
            }

            const isFullKm = Math.abs(targetKm - Math.round(targetKm)) < 0.01;
            const maxDiff = isFullKm ? 500 : 250;
            const isHalfKm = !isFullKm;

            if (isHalfKm && !this.features.halfKmMarkers) continue;

            if (closestIdx >= 0 && minDiff <= maxDiff) {
                const [sx, sy] = this._toScreen(u[closestIdx], v[closestIdx]);
                const radius = isFullKm ? 12 : 10;
                const color = isFullKm ? '#3366cc' : '#888888';

                ctx.fillStyle = color;
                ctx.beginPath(); ctx.arc(sx, sy, radius, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = '#000';
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.arc(sx, sy, radius, 0, Math.PI * 2); ctx.stroke();

                let label = isFullKm ? Math.round(targetKm) + '' : (Math.abs(targetKm - 0.5) < 0.01 ? '.5' : Math.floor(targetKm) + '');
                ctx.fillStyle = '#fff';
                ctx.font = 'bold 10px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(label, sx, sy);
            }
        }
    }

    _drawStormMotion() {
        const [sx, sy] = this._toScreen(this.stormMotion.u, this.stormMotion.v);
        const ctx = this.ctx;
        ctx.fillStyle = '#cc0000';
        ctx.beginPath();
        const size = 8;
        ctx.moveTo(sx, sy - size);
        ctx.lineTo(sx - size, sy + size);
        ctx.lineTo(sx + size, sy + size);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = '#660000';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#cc0000';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.fillText('SM', sx + 10, sy - 2);
    }

    _drawSurfaceWind() {
        const [sx, sy] = this._toScreen(this.metarData.u, this.metarData.v);
        const ctx = this.ctx;
        ctx.fillStyle = '#000';
        ctx.beginPath(); ctx.arc(sx, sy, 7, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(sx, sy, 7, 0, Math.PI * 2); ctx.stroke();

        ctx.fillStyle = '#fff';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('S', sx, sy);
    }

    _drawSRH() {
        const ctx = this.ctx;
        const u = this.data.u_components;
        const v = this.data.v_components;
        const heights = this.data.heights;

        const allU = [this.metarData.u, ...u];
        const allV = [this.metarData.v, ...v];
        const allH = [0, ...heights.map(h => h * 1000)];

        this._fillSRHPoly(ctx, allU, allV, allH, 1000, 'rgba(144, 238, 144, 0.3)');
        this._fillSRHPoly(ctx, allU, allV, allH, 3000, 'rgba(173, 216, 230, 0.2)');
    }

    _fillSRHPoly(ctx, allU, allV, allH, maxHeight, color) {
        const pts = [];
        for (let i = 0; i < allU.length; i++) {
            if (allH[i] <= maxHeight) pts.push(this._toScreen(allU[i], allV[i]));
        }
        if (pts.length < 3) return;
        const smPt = this._toScreen(this.stormMotion.u, this.stormMotion.v);
        pts.push(smPt);
        pts.push(pts[0]);

        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
        ctx.closePath();
        ctx.fill();
    }

    _drawShearVector() {
        const ctx = this.ctx;
        if (!this.metarData || this.data.u_components.length === 0) return;

        const surfU = this.metarData.u, surfV = this.metarData.v;
        const refU = this.data.u_components[0] - surfU;
        const refV = this.data.v_components[0] - surfV;
        const pts = [[surfU, surfV]];

        for (let i = 0; i < this.data.u_components.length; i++) {
            const vecU = this.data.u_components[i] - surfU;
            const vecV = this.data.v_components[i] - surfV;
            const magRef = Math.sqrt(refU * refU + refV * refV);
            const magVec = Math.sqrt(vecU * vecU + vecV * vecV);
            if (magRef > 0 && magVec > 0) {
                const cosA = Math.max(-1, Math.min(1, (refU * vecU + refV * vecV) / (magRef * magVec)));
                const angle = Math.acos(cosA) * 180 / Math.PI;
                if (angle <= 10) pts.push([this.data.u_components[i], this.data.v_components[i]]);
                else break;
            }
        }

        if (pts.length > 1) {
            ctx.strokeStyle = 'rgba(0, 180, 0, 0.7)';
            ctx.lineWidth = 4;
            ctx.beginPath();
            const [x0, y0] = this._toScreen(pts[0][0], pts[0][1]);
            ctx.moveTo(x0, y0);
            for (let i = 1; i < pts.length; i++) {
                const [x, y] = this._toScreen(pts[i][0], pts[i][1]);
                ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        this._shearPoints = pts;
    }

    _drawCriticalAngle() {
        const ctx = this.ctx;
        if (!this.metarData || !this.stormMotion) return;
        const params = this.data ? this.data.parameters : null;
        const surfU = this.metarData.u, surfV = this.metarData.v;
        const [sx1, sy1] = this._toScreen(surfU, surfV);
        const [sx2, sy2] = this._toScreen(this.stormMotion.u, this.stormMotion.v);

        ctx.strokeStyle = 'rgba(200, 0, 0, 0.7)';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke();
        ctx.setLineDash([]);

        if (params && params.vad_1km_point) {
            const [ex, ey] = this._toScreen(params.vad_1km_point.u, params.vad_1km_point.v);
            ctx.strokeStyle = 'rgba(0, 0, 200, 0.7)';
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 4]);
            ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(ex, ey); ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = 'rgba(0, 0, 200, 0.9)';
            ctx.font = 'bold 9px sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            ctx.fillText('1km', ex + 6, ey - 2);
        }

        if (params && params.kink_point) {
            const [kx, ky] = this._toScreen(params.kink_point.u, params.kink_point.v);
            ctx.strokeStyle = 'rgba(180, 0, 180, 0.7)';
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 3]);
            ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(kx, ky); ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = 'rgba(180, 0, 180, 0.9)';
            ctx.font = 'bold 9px sans-serif';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            ctx.fillText('kink', kx + 6, ky - 2);
        }
    }

    _drawParamText() {
        const ctx = this.ctx;
        const params = this.data.parameters;
        if (!params || Object.keys(params).length === 0) return;

        const lines = [];
        if (params.shear_1km != null) lines.push(`0-1km Shear: ${params.shear_1km} kt`);
        if (params.shear_3km != null) lines.push(`0-3km Shear: ${params.shear_3km} kt`);
        if (this.stormMotion) lines.push(`Storm Motion: ${this.stormMotion.direction.toFixed(0)}°/${this.stormMotion.speed.toFixed(0)}kt`);
        if (params.bunkers_rm) lines.push(`Bunkers RM: ${params.bunkers_rm.direction.toFixed(0)}°/${params.bunkers_rm.speed.toFixed(0)}kt`);
        if (params.esterheld_angle != null) lines.push(`Esterheld Angle: ${params.esterheld_angle}°`);
        if (params.skoff_angle != null) lines.push(`Skoff Angle: ${params.skoff_angle}°`);
        if (params.srh_0_1 != null) lines.push(`SRH 0-1km: ${params.srh_0_1} m²/s²`);
        if (params.srh_0_3 != null) lines.push(`SRH 0-3km: ${params.srh_0_3} m²/s²`);

        if (lines.length === 0) return;

        const x = 12, y = 60;
        const lineH = 16;
        const padding = 8;

        ctx.font = '11px monospace';
        const maxW = Math.max(...lines.map(l => ctx.measureText(l).width));
        const boxW = maxW + padding * 2;
        const boxH = lines.length * lineH + padding * 2;

        ctx.fillStyle = 'rgba(200, 225, 255, 0.85)';
        ctx.strokeStyle = '#99b';
        ctx.lineWidth = 1;
        this._roundRect(ctx, x, y, boxW, boxH, 6);

        ctx.fillStyle = '#222';
        ctx.font = '11px monospace';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        for (let i = 0; i < lines.length; i++) {
            ctx.fillText(lines[i], x + padding, y + padding + i * lineH);
        }
    }

    _roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.arcTo(x + w, y, x + w, y + r, r);
        ctx.lineTo(x + w, y + h - r);
        ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
        ctx.lineTo(x + r, y + h);
        ctx.arcTo(x, y + h, x, y + h - r, r);
        ctx.lineTo(x, y + r);
        ctx.arcTo(x, y, x + r, y, r);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
    }

    _drawTitle() {
        const ctx = this.ctx;
        let title = '';
        if (this.data.site_id && this.data.site_name) title = `${this.data.site_id} - ${this.data.site_name}`;
        if (this.data.valid_time) title += (title ? '  |  ' : '') + `Valid: ${this.data.valid_time}`;

        if (!title) return;

        ctx.fillStyle = '#222';
        ctx.font = 'bold 13px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(title, this.width / 2, 8);

        if (this.metarData && this.metarStation) {
            const metarLine = `Surface Wind: ${this.metarData.direction}°/${this.metarData.speed}kt (${this.metarStation})`;
            ctx.font = '11px sans-serif';
            ctx.fillText(metarLine, this.width / 2, 26);
        }
    }

    _drawTooltip() {
        const idx = this.hoveredPoint;
        if (idx === null || !this.data) return;

        const u = this.data.u_components[idx];
        const v = this.data.v_components[idx];
        const h = this.data.heights[idx];
        const spd = this.data.speeds[idx];
        const dir = this.data.directions[idx];
        const [sx, sy] = this._toScreen(u, v);

        const ctx = this.ctx;
        const lines = [
            `Height: ${(h * 1000).toFixed(0)}m (${(h * 3.28084).toFixed(0)}ft)`,
            `Wind: ${dir.toFixed(0)}° @ ${spd.toFixed(0)}kt`,
            `U: ${u.toFixed(1)}  V: ${v.toFixed(1)}`
        ];

        ctx.font = '11px monospace';
        const maxW = Math.max(...lines.map(l => ctx.measureText(l).width));
        const padding = 6;
        const lineH = 15;
        const boxW = maxW + padding * 2;
        const boxH = lines.length * lineH + padding * 2;

        let tx = sx + 15;
        let ty = sy - boxH / 2;
        if (tx + boxW > this.width) tx = sx - boxW - 15;
        if (ty < 0) ty = 5;
        if (ty + boxH > this.height) ty = this.height - boxH - 5;

        ctx.fillStyle = 'rgba(255, 255, 240, 0.95)';
        ctx.strokeStyle = '#666';
        ctx.lineWidth = 1;
        this._roundRect(ctx, tx, ty, boxW, boxH, 4);

        ctx.fillStyle = '#222';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        for (let i = 0; i < lines.length; i++) {
            ctx.fillText(lines[i], tx + padding, ty + padding + i * lineH);
        }

        ctx.fillStyle = '#ff4444';
        ctx.beginPath(); ctx.arc(sx, sy, 6, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(sx, sy, 6, 0, Math.PI * 2); ctx.stroke();
    }

    _drawZoomInfo() {
        const ctx = this.ctx;
        const zoomText = `Zoom: ${this.scale.toFixed(1)}x`;
        ctx.fillStyle = 'rgba(0,0,0,0.5)';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText(zoomText, this.width - 8, this.height - 8);

        ctx.fillStyle = 'rgba(0,0,0,0.35)';
        ctx.font = '9px sans-serif';
        ctx.fillText('Scroll to zoom · Drag to pan · Hover for info', this.width - 8, this.height - 22);
    }
}
