"use client";

import { useRef, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import styles from "./Navigation.module.scss";

export const Navigation = ({ activeSection, isSolid }) => {
  const navRef = useRef(null);
  const isDragging = useRef(false);
  const startX = useRef(0);
  const scrollLeft = useRef(0);
  const velocity = useRef(0);
  const lastX = useRef(0);
  const lastTime = useRef(0);
  const [dotStyles, setDotStyles] = useState([]);

  const sections = [
    { id: "bron", label: "Бронь" },
    { id: "gallery", label: "Галерея" },
    { id: "menu", label: "Меню" },
    { id: "about", label: "О месте" },
    { id: "chef", label: "О шефе" },
    { id: "events", label: "Мероприятия" },
    { id: "map", label: "Карта" },
  ];

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;

    const updateDots = () => {
      const maxScroll = nav.scrollWidth - nav.clientWidth;
      if (maxScroll <= 0) {
        setDotStyles([]);
        return;
      }

      const scrollRatio = nav.scrollLeft / maxScroll;
      const newDotStyles = sections.map((_, index) => {
        const dotPosition = index / (sections.length - 1);
        const distance = Math.abs(scrollRatio - dotPosition);
        const scale = 1 - Math.min(distance * 4, 0.5);
        const opacity = 1 - Math.min(distance * 3, 0.6);
        return { scale, opacity, isActive: scale > 0.75 };
      });
      setDotStyles(newDotStyles);
    };

    const centerActiveLink = () => {
      const activeLink = nav.querySelector(`.${styles.active}`);
      if (activeLink) {
        const navRect = nav.getBoundingClientRect();
        const linkRect = activeLink.getBoundingClientRect();
        const scrollTo =
          linkRect.left -
          navRect.left +
          nav.scrollLeft -
          nav.clientWidth / 2 +
          linkRect.width / 2;
        nav.scrollTo({ left: scrollTo, behavior: "smooth" });
      }
    };

    const handleTouchStart = (e) => {
      isDragging.current = true;
      startX.current = e.touches[0].pageX - scrollLeft.current;
      velocity.current = 0;
      lastX.current = e.touches[0].pageX;
      lastTime.current = Date.now();
    };

    const handleTouchMove = (e) => {
      if (!isDragging.current) return;
      e.preventDefault();

      const x = e.touches[0].pageX;
      const deltaX = x - lastX.current;
      const time = Date.now();
      const deltaTime = time - lastTime.current || 1;
      velocity.current = deltaX / deltaTime;

      const walk = x - startX.current;
      const maxScroll = nav.scrollWidth - nav.clientWidth;
      let translateX = 0;

      if (walk > 0) {
        translateX = Math.min(walk * 0.5, 150);
      } else if (walk < -maxScroll) {
        translateX = Math.max((walk + maxScroll) * 0.5, -150);
      } else {
        translateX = 0;
        scrollLeft.current = walk;
        nav.scrollLeft = -walk;
      }

      nav.style.transform = `translateX(${translateX}px)`;
      lastX.current = x;
      lastTime.current = time;
      updateDots();
    };

    const handleTouchEnd = () => {
      if (!isDragging.current) return;
      isDragging.current = false;

      nav.style.transform = "translateX(0)";
      const maxScroll = nav.scrollWidth - nav.clientWidth;
      const newScrollLeft = Math.min(
        0,
        Math.max(-maxScroll, scrollLeft.current + velocity.current * 100)
      );
      scrollLeft.current = newScrollLeft;
      nav.scrollLeft = -newScrollLeft;
      updateDots();
    };

    const handleMouseDown = (e) => {
      isDragging.current = true;
      startX.current = e.pageX - scrollLeft.current;
      velocity.current = 0;
      lastX.current = e.pageX;
      lastTime.current = Date.now();
    };

    const handleMouseMove = (e) => {
      if (!isDragging.current) return;
      e.preventDefault();

      const x = e.pageX;
      const deltaX = x - lastX.current;
      const time = Date.now();
      const deltaTime = time - lastTime.current || 1;
      velocity.current = deltaX / deltaTime;

      const walk = x - startX.current;
      const maxScroll = nav.scrollWidth - nav.clientWidth;
      let translateX = 0;

      if (walk > 0) {
        translateX = Math.min(walk * 0.5, 150);
      } else if (walk < -maxScroll) {
        translateX = Math.max((walk + maxScroll) * 0.5, -150);
      } else {
        translateX = 0;
        scrollLeft.current = walk;
        nav.scrollLeft = -walk;
      }

      nav.style.transform = `translateX(${translateX}px)`;
      lastX.current = x;
      lastTime.current = time;
      updateDots();
    };

    const handleMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;

      nav.style.transform = "translateX(0)";
      const maxScroll = nav.scrollWidth - nav.clientWidth;
      const newScrollLeft = Math.min(
        0,
        Math.max(-maxScroll, scrollLeft.current + velocity.current * 100)
      );
      scrollLeft.current = newScrollLeft;
      nav.scrollLeft = -newScrollLeft;
      updateDots();
    };

    nav.addEventListener("touchstart", handleTouchStart);
    nav.addEventListener("touchmove", handleTouchMove);
    nav.addEventListener("touchend", handleTouchEnd);
    nav.addEventListener("mousedown", handleMouseDown);
    nav.addEventListener("mousemove", handleMouseMove);
    nav.addEventListener("mouseup", handleMouseUp);
    nav.addEventListener("mouseleave", handleMouseUp);
    nav.addEventListener("scroll", updateDots);

    centerActiveLink();
    updateDots();

    return () => {
      nav.removeEventListener("touchstart", handleTouchStart);
      nav.removeEventListener("touchmove", handleTouchMove);
      nav.removeEventListener("touchend", handleTouchEnd);
      nav.removeEventListener("mousedown", handleMouseDown);
      nav.removeEventListener("mousemove", handleMouseMove);
      nav.removeEventListener("mouseup", handleMouseUp);
      nav.removeEventListener("mouseleave", handleMouseUp);
      nav.removeEventListener("scroll", updateDots);
    };
  }, [activeSection]);

  const navVariants = {
    initial: { opacity: 0, y: 10 },
    animate: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.6,
        ease: "easeOut",
        type: "spring",
        stiffness: 80,
      },
    },
    stuck: {
      position: "fixed",
      top: 60,
      opacity: 1,
      boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
      transition: { duration: 0.3, ease: "easeOut" },
    },
    transparent: {
      position: "relative",
      top: 0,
      opacity: 1,
      boxShadow: "none",
      transition: { duration: 0.3, ease: "easeOut" },
    },
  };

  const linkVariants = {
    hover: {
      scale: 1.05,
      color: "#111827",
      transition: { type: "spring", stiffness: 200 },
    },
    active: {
      fontWeight: 700,
      color: "#111827",
      transition: { duration: 0.2, ease: "easeOut" },
    },
  };

  const dotVariants = (isActive) => ({
    animate: {
      scale: isActive ? 1 : 0.5,
      opacity: isActive ? 1 : 0.4,
      backgroundColor: isActive ? "#111827" : "#d1d5db",
      transition: { duration: 0.3, ease: "easeOut" },
    },
  });

  return (
    <motion.div
      className={styles.navWrapper}
      variants={navVariants}
      initial="initial"
      animate={isSolid ? "stuck" : "transparent"}
    >
      <nav ref={navRef} className={styles.nav}>
        {sections.map((section) => (
          <Link
            key={section.id}
            href={`#${section.id}`}
            className={`${styles.link} ${
              activeSection === section.id ? styles.active : ""
            }`}
          >
            <motion.div
              variants={linkVariants}
              whileHover="hover"
              animate={activeSection === section.id ? "active" : ""}
            >
              {section.label}
            </motion.div>
          </Link>
        ))}
      </nav>
    </motion.div>
  );
};
