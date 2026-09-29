FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./

ARG VITE_API_URL=http://localhost:8007
ARG VITE_MEDIA_URL=http://localhost:3006
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_MEDIA_URL=$VITE_MEDIA_URL

RUN npm run build


FROM nginx:alpine AS runtime

COPY docker/app.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3007

CMD ["nginx", "-g", "daemon off;"]
