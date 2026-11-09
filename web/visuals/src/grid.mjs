import * as THREE from "three";

// View coordinates only. This plane supplies depth; it is not experiment data.
export function createContextGrid() {
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    uniforms: {
      tint: { value: new THREE.Color("#a0a597") },
      radius: { value: 12 },
    },
    vertexShader: `varying vec2 ground;
      void main(){ground=position.xy;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `varying vec2 ground;
      uniform vec3 tint; uniform float radius;
      float stroke(float pitch){
        vec2 p=ground/pitch;
        vec2 edge=abs(fract(p+0.5)-0.5)/max(fwidth(p),vec2(0.0001));
        return 1.0-smoothstep(0.3,1.0,min(edge.x,edge.y));
      }
      void main(){
        float envelope=pow(max(0.0,1.0-length(ground)/radius),1.8);
        float alpha=(stroke(0.5)*0.012+stroke(2.5)*0.009)*envelope;
        if(alpha<0.0008)discard;
        gl_FragColor=vec4(tint,alpha);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.renderOrder = -10;
  return mesh;
}
